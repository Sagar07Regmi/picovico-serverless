# src/seatunlock/app.py
import os, json, boto3
from botocore.exceptions import ClientError

dynamodb = boto3.client("dynamodb")
TABLE = os.environ.get("SEAT_LOCK_TABLE")

def lambda_handler(event, context):
    # event: { bookingId, showId, seats: [] }
    show_id = event.get("showId")
    seats = event.get("seats", [])
    if not show_id or not seats:
        return {"ok": False, "reason": "missing showId or seats"}
    released = []
    for s in seats:
        try:
            dynamodb.delete_item(TableName=TABLE, Key={"showId": {"S": show_id}, "seatId": {"S": s}})
            released.append(s)
        except ClientError as e:
            print("delete failed for", s, e)
    return {"ok": True, "released": released}
