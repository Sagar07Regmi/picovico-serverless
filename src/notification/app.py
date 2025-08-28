import os, json, boto3
from botocore.exceptions import ClientError

sns = boto3.client("sns")
ses = boto3.client("ses")
TOPIC_ARN = os.environ.get("NOTIFICATION_TOPIC")

def send_email_ses(from_addr, to_address, subject, body):
    try:
        ses.send_email(
            Source=from_addr,
            Destination={'ToAddresses': [to_address]},
            Message={'Subject': {'Data': subject}, 'Body': {'Text': {'Data': body}}}
        )
    except ClientError as e:
        print("SES send failed:", e)
        return False
    return True

def lambda_handler(event, context):
    booking_id = event.get("bookingId")
    status = event.get("status")
    ticket_url = event.get("ticketUrl")
    customer_id = event.get("customerId", "unknown")

    msg = {"bookingId": booking_id, "status": status, "ticketUrl": ticket_url, "customerId": customer_id}
    try:
        sns.publish(TopicArn=TOPIC_ARN, Message=json.dumps(msg), Subject=f"Booking {status}: {booking_id}")
    except ClientError as e:
        print("SNS publish error:", e)

    # If customerId looks like an email, attempt SES (SES must be configured/verified)
    if "@" in str(customer_id):
        from_address = customer_id  # WARNING: in sandbox you must use verified addresses
        subject = f"Your ticket {booking_id} - status {status}"
        body = f"Booking status: {status}\nTicket URL: {ticket_url or 'N/A'}"
        send_email_ses(from_address, customer_id, subject, body)

    return {"ok": True}
