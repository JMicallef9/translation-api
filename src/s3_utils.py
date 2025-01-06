import json
import boto3

def save_to_s3(data, bucket_name):
    
    s3 = boto3.client('s3', region_name='eu-west-2')
    
    data_json = json.dumps(data)

    s3.put_object(Bucket=bucket_name,
                         Body=data_json,
                         Key=data['timestamp'])