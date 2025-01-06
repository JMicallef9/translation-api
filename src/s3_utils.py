import json

def save_to_s3(data, s3_client, bucket_name):
    data_json = json.dumps(data)
    
    s3_client.put_object(Bucket=bucket_name,
                         Body=data_json,
                         Key=data['timestamp'])