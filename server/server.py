import os
import sys
# 添加父目录的父目录到系统路径 (指向 Card/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from concurrent import futures
import threading
import time

from proto import cs_pb2_grpc
import grpc

from gameplay import Gameplay
from servicer import CSServicer

def run_server(gameplay, port=50051):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    cs_pb2_grpc.add_CSServicer_to_server(CSServicer(gameplay), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"CSServicer open at {port} port")
    
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