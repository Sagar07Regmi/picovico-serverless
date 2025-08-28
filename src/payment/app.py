import os, json, time, boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
BOOKING_TABLE = os.environ.get("BOOKING_TABLE")
table = dynamodb.Table(BOOKING_TABLE) if BOOKING_TABLE else None

def process_payment_mock(amount, simulate=None):
    time.sleep(1)
    if simulate == "fail":
        return {"status": "FAILED", "reason": "simulated-failure"}
    return {"status": "PAID", "txId": f"mock-tx-{int(time.time())}"}

def lambda_handler(event, context):
    booking_id = event.get("bookingId")
    amount = event.get("amount", 0)
    simulate = event.get("simulate")
    result = process_payment_mock(amount, simulate=simulate)
    # Update booking status
    if table and booking_id:
        try:
            status = "PAID" if result.get("status") == "PAID" else "FAILED"
            table.update_item(Key={"bookingId": booking_id}, UpdateExpression="SET #s = :s, paymentResult = :p", ExpressionAttributeNames={"#s":"status"}, ExpressionAttributeValues={":s": status, ":p": result})
        except ClientError as e:
            print("DynamoDB update failed:", e)
    return result
