import grpc

import os
import sys
# 添加父目录的父目录到系统路径 (指向 Card/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proto import cs_pb2
from proto import cs_pb2_grpc
from gameplay import Event
from gameplay import EventType

from concurrent import futures
import threading
import time

from gameplay import Gameplay

class CSServicer(cs_pb2_grpc.CSServicer):
    def __init__(self, gameplay: Gameplay):
        self.gameplay = gameplay
    
    def Heartbeat(self, request, context):
        # print("recv message:", request)
        return cs_pb2.CSResHeartbeat()
    
    def JoinPlayer(self, request: cs_pb2.CSReqJoinPlayer, context):
        # print("recv message:", request)
        self.gameplay.join_player(request.uid, request.name, request.chips)
        return cs_pb2.CSResJoinPlayer()
    
    def StartGameplay(self, request: cs_pb2.CSReqStartGameplay, context):
        # print("recv message:", request)
        self.gameplay.set_start_state()
        return cs_pb2.CSResStartGameplay()

def run_server(gameplay, port=50051):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    cs_pb2_grpc.add_CSServicer_to_server(CSServicer(gameplay), server)
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


if __name__ == "__main__":
    main()