import grpc

import os
import sys
# 添加父目录的父目录到系统路径 (指向 Card/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proto import cs_pb2
from proto import cs_pb2_grpc

from concurrent import futures
import threading
import time

from gameplay import Gameplay

class CSServicer(cs_pb2_grpc.CSServicer):
    def __init__(self):
        self.db = {}
    
    def Hello(self, req, context):
        print("recv message:", req.message)
        return cs_pb2.CSHelloRsp(message=req.message)

def run_server(gameplay, port=50051):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    cs_pb2_grpc.add_CSServicer_to_server(CSServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print("server start at", port)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("keyboard interrupt")
    finally:
        server.stop(0).wait()
        print("grpc server stop")

def main():
    gameplay = Gameplay()
    
    try:
        grpc_thread = threading.Thread(target=run_server, args=(gameplay,), daemon=True)
        grpc_thread.start()
        
        gameplay.start()
    except KeyboardInterrupt:
        print("keyboard interrupt")
    finally:
        gameplay.stop()
        
    # gameplay.join_player("player1", 1000)
    # gameplay.join_player("player2", 1000)
    # gameplay.join_player("player3", 1000)
    
    # gameplay.init_gameplay()
    # gameplay.flop_card()
    # gameplay.turn_card()
    # gameplay.river_card()
    
    # server.wait_for_termination()


if __name__ == "__main__":
    main()