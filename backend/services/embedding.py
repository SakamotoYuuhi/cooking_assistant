import boto3
import json
import os
from typing import List

# Bedrock Titan Embeddings V2 を使用
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"


def get_bedrock_client():
    return boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def embed_text(text: str) -> List[float]:
    """テキスト1件をEmbeddingベクトルに変換する"""
    client = get_bedrock_client()

    response = client.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "inputText": text,
            "dimensions": 512,   # 512次元（軽量・高速）
            "normalize": True,
        }),
    )

    result = json.loads(response["body"].read())
    return result["embedding"]


def embed_texts(texts: List[str]) -> List[List[float]]:
    """複数テキストをまとめてEmbeddingに変換する"""
    return [embed_text(t) for t in texts]
