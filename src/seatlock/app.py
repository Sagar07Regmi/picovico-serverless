import os, json, time
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.client("dynamodb")
TABLE = os.environ["SEAT_LOCK_TABLE"]
LOCK_TTL = 15 * 60

def lambda_handler(event, context):
    if isinstance(event, str):
        event = json.loads(event)
    show_id, seats, booking_id = event.get("showId"), event.get("seats", []), event.get("bookingId")
    if not show_id or not seats:
        return {"locked": False, "reason": "missing showId or seats"}

    ts, ttl = int(time.time()), int(time.time())+LOCK_TTL
    locked, failed = [], []

    for seat_id in seats:
        try:
            dynamodb.put_item(
                TableName=TABLE,
                Item={
                    "showId": {"S": show_id},
                    "seatId": {"S": seat_id},
                    "bookingId": {"S": booking_id},
                    "lockedAt": {"N": str(ts)},
                    "ttl": {"N": str(ttl)}
                },
                ConditionExpression="attribute_not_exists(showId) AND attribute_not_exists(seatId)"
            )
            locked.append(seat_id)
        except ClientError:
            failed.append(seat_id)

    if failed:
        for s in locked:
            dynamodb.delete_item(TableName=TABLE, Key={"showId": {"S": show_id}, "seatId": {"S": s}})
        return {"locked": False, "failed": failed}
    return {"locked": True, "lockedSeats": locked}
