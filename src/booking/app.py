# src/booking/app.py
import os, json, uuid, time, boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")
sfn = boto3.client("stepfunctions")
events = boto3.client("events")

BOOKING_TABLE = os.environ["BOOKING_TABLE"]
SEAT_LOCK_FN = os.environ["SEAT_LOCK_FUNCTION"]
PAYMENT_SFN_ARN = os.environ["PAYMENT_STATE_MACHINE_ARN"]
EVENT_BUS = os.environ.get("EVENT_BUS_NAME", "default")

table = dynamodb.Table(BOOKING_TABLE)

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except:
        return {"statusCode": 400, "body": json.dumps({"message": "invalid JSON"})}

    show_id, seats = body.get("showId"), body.get("seats")
    customer_id = body.get("customerId") or "anonymous"
    if not show_id or not seats:
        return {"statusCode": 400, "body": json.dumps({"message": "showId and seats required"})}

    booking_id = str(uuid.uuid4())
    now = int(time.time())

    item = {
        "bookingId": booking_id,
        "customerId": customer_id,
        "showId": show_id,
        "seats": seats,
        "status": "PENDING",
        "createdAt": now,
        "updatedAt": now,
        "expiresAt": now + 15*60
    }
    try:
        table.put_item(Item=item)
    except ClientError as e:
        return {"statusCode": 500, "body": json.dumps({"message":"failed to create booking"})}

    # call SeatLock Lambda synchronously
    try:
        payload = {"bookingId": booking_id, "showId": show_id, "seats": seats, "customerId": customer_id}
        resp = lambda_client.invoke(FunctionName=SEAT_LOCK_FN, InvocationType="RequestResponse", Payload=json.dumps(payload))
        result = json.loads(resp["Payload"].read())
    except Exception as e:
        table.update_item(Key={"bookingId": booking_id}, UpdateExpression="SET #s=:s", ExpressionAttributeNames={"#s":"status"}, ExpressionAttributeValues={":s":"FAILED"})
        return {"statusCode": 500, "body": json.dumps({"message":"seat lock invocation failed"})}

    if result.get("locked"):
        sfn_input = {
            "bookingId": booking_id,
            "customerId": customer_id,
            "showId": show_id,
            "seats": seats,
            "amount": body.get("amount", 0),
            "simulate": body.get("simulate")  # optional: "success" | "fail"
        }
        try:
            sfn.start_execution(stateMachineArn=PAYMENT_SFN_ARN, input=json.dumps(sfn_input), name=f"{booking_id}-{now}")
        except Exception as e:
            table.update_item(Key={"bookingId": booking_id}, UpdateExpression="SET #s=:s", ExpressionAttributeNames={"#s":"status"}, ExpressionAttributeValues={":s":"FAILED"})
            return {"statusCode":500, "body": json.dumps({"message":"failed to start payment workflow"})}

        # emit booking.created event
        try:
            events.put_events(Entries=[{
                "EventBusName": EVENT_BUS,
                "Source": "picovico.booking",
                "DetailType": "BookingCreated",
                "Detail": json.dumps({"bookingId": booking_id, "showId": show_id, "seats": seats})
            }])
        except Exception:
            pass

        return {"statusCode":202, "body": json.dumps({"bookingId": booking_id, "status":"LOCKED"})}
    else:
        table.update_item(Key={"bookingId": booking_id}, UpdateExpression="SET #s=:s", ExpressionAttributeNames={"#s":"status"}, ExpressionAttributeValues={":s":"FAILED"})
        return {"statusCode":409, "body": json.dumps({"message":"seats unavailable"})}
