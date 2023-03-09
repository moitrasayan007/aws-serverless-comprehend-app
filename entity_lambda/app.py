import json
import hashlib
import os
import boto3
import logging
import redis

# Set up logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_redis():
  redis_config = {
    "host": os.environ['REDIS_ENDPOINT'],
    "port": 6379,
    "db": 0,
    "ssl": True,
    "ssl_cert_reqs": None
  }
  return redis.Redis(**redis_config)


def lambda_handler(event, context):
    nlp_payload = json.loads(event['body'])
    text_to_analyse = nlp_payload['body']
    logger.info("Analysing: {text}".format(text=text_to_analyse))

    # Set up Redis configuration, check cache
    r = get_redis()
    hash_text = hashlib.md5(text_to_analyse.encode('utf-8')).hexdigest()
    nlp_entities = r.get(hash_text)
    cache_hit = True

    comprehend = boto3.client('comprehend', endpoint_url='https://comprehend.{}.amazonaws.com/'.format(os.environ['REGION']))

    if nlp_entities == None:
        # Use AWS comprehend to extract entities from our text
        nlp = comprehend.detect_entities(Text = text_to_analyse, LanguageCode='en')
        nlp_entities = nlp['Entities']
        cache_hit = False
        # Update cache, expires in 1 hour
        r.set(hash_text, json.dumps(nlp_entities), ex=3600)
    else:
        # Entities stored in JSON in cache
        nlp_entities = json.loads(nlp_entities)

    # Put message on queue to be handled by another function
    queue_msg_body = json.dumps({
        "hashed_key": hash_text,
        "entities": nlp_entities
    })
    sqs = boto3.client(
        'sqs', endpoint_url='https://sqs.{}.amazonaws.com/'.format(os.environ['REGION']))
    sqs.send_message(
        QueueUrl = "https://sqs.{}.amazonaws.com/{}/{}".format(
            os.environ['REGION'],
            os.environ['ACCOUNT_ID'],
            os.environ['QUEUE_NAME']
        ),
        MessageBody = queue_msg_body)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "text": text_to_analyse,
            "entities": nlp_entities,
            "cache_hit": cache_hit
        }),
    }
