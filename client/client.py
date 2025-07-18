import grpc

import os
import sys
# 添加父目录的父目录到系统路径 (指向 Card/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proto import cs_pb2
from proto import cs_pb2_grpc

def main():
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = cs_pb2_grpc.CSStub(channel)
        print("send message:Hello")
        stub.Hello(cs_pb2.CSHelloReq(message="Hello"))
        
if __name__ == "__main__":
    main()