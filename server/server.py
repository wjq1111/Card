import grpc

import os
import sys
# 添加父目录的父目录到系统路径 (指向 Card/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proto import cs_pb2
from proto import cs_pb2_grpc

from concurrent import futures

class CSServicer(cs_pb2_grpc.CSServicer):
    def __init__(self):
        self.db = {}
    
    def Hello(self, req, context):
        print("recv message:", req.message)
        return cs_pb2.CSHelloRsp(message=req.message)

def main():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    cs_pb2_grpc.add_CSServicer_to_server(CSServicer(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    main()