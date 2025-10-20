# rabbitmq_publisher.py
import json, os, pika
from dotenv import load_dotenv

load_dotenv()
RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/%2F")
RECO_EXCHANGE = os.getenv("RABBIT_RECO_EXCHANGE", "recommendations")

def publish_recommendation(payload: dict):
    try:
        params = pika.URLParameters(RABBIT_URL)
        conn = pika.BlockingConnection(params)
        ch = conn.channel()
        ch.exchange_declare(exchange=RECO_EXCHANGE, exchange_type="topic", durable=True)
        ch.basic_publish(
            exchange=RECO_EXCHANGE,
            routing_key="",
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        print(f"📤 Recommendation → Published to '{RECO_EXCHANGE}'")
        conn.close()
    except Exception as e:
        print("⚠️ RabbitMQ publish failed:", e)
