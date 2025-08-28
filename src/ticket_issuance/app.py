import os, json, io, boto3, qrcode
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
TICKET_BUCKET = os.environ["TICKET_BUCKET"]
BOOKING_TABLE = os.environ["BOOKING_TABLE"]
booking_table = dynamodb.Table(BOOKING_TABLE)

def generate_qr_image(data: str):
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio

def generate_pdf_with_qr(booking_id, customer_id, show_id, seats, qr_bytes_io):
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    c.setFont("Helvetica", 12)
    c.drawString(100, 700, f"Picovico Ticket")
    c.drawString(100, 680, f"Booking: {booking_id}")
    c.drawString(100, 660, f"Customer: {customer_id}")
    c.drawString(100, 640, f"Show: {show_id}")
    c.drawString(100, 620, f"Seats: {','.join(seats)}")
    from reportlab.lib.utils import ImageReader
    qr_img = qr_bytes_io
    qr_img.seek(0)
    image = ImageReader(qr_img)
    c.drawImage(image, 100, 450, width=150, height=150)
    c.showPage()
    c.save()
    packet.seek(0)
    return packet

def upload_to_s3(bucket, key, body, content_type="application/pdf"):
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    url = s3.generate_presigned_url('get_object', Params={'Bucket': bucket, 'Key': key}, ExpiresIn=3600)
    return url

def lambda_handler(event, context):
    booking_id = event.get("bookingId")
    customer_id = event.get("customerId")
    show_id = event.get("showId")
    seats = event.get("seats", [])
    if not booking_id:
        return {"error": "missing bookingId"}

    qr_payload = json.dumps({"bookingId": booking_id, "customerId": customer_id, "issuedAt": datetime.utcnow().isoformat()})
    qr_img_io = generate_qr_image(qr_payload)
    pdf_io = generate_pdf_with_qr(booking_id, customer_id, show_id, seats, qr_img_io)

    key = f"tickets/{booking_id}.pdf"
    presigned = upload_to_s3(TICKET_BUCKET, key, pdf_io.getvalue(), content_type="application/pdf")

    try:
        booking_table.update_item(Key={"bookingId": booking_id}, UpdateExpression="SET ticketUrl=:u, updatedAt=:t", ExpressionAttributeValues={":u": presigned, ":t": int(datetime.utcnow().timestamp())})
    except ClientError as e:
        print("DDB update failed:", e)

    return {"ticketUrl": presigned, "s3key": key}
