
import os
import sys
# 添加父目录的父目录到系统路径 (指向 Card/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
import socket

import grpc
from proto import cs_pb2
from proto import cs_pb2_grpc
from concurrent import futures
from servicer import SCServicer

# IP = "111.229.201.75"
IP = "localhost"
SERVER_PORT = 50051

# 本机测试，端口不能一致
PORT = 50052
UID = 0

def get_all_local_ips():
    """获取所有网络接口的IP地址（不包括127.0.0.1）"""
    ips = []
    hostname = socket.gethostname()
    try:
        # 获取所有关联的IP地址
        for addr in socket.getaddrinfo(hostname, None):
            # addr[4]是(ip, port)元组
            ip = addr[4][0]
            # 过滤IPv6和回环地址
            if ':' not in ip and not ip.startswith('127.'):
                ips.append(ip)
        return list(set(ips))  # 去重
    except:
        return ["127.0.0.1"]

def main():
    arguments = sys.argv[1:]
    if arguments:
        PORT = arguments[0]
    
    # 发给server的stub
    channel = grpc.insecure_channel(f"{IP}:{SERVER_PORT}")
    stub = cs_pb2_grpc.CSStub(channel)
    
    # server发给自己的service
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    cs_pb2_grpc.add_SCServicer_to_server(SCServicer(), server)
    server.add_insecure_port(f"[::]:{PORT}")
    server.start()
    print(f"client service start at {PORT}")

    try:
        while True:
            user_input = input()
            if user_input in ["exit", "quit"]:
                print("client stop")
                break
            elif user_input == "join":
                print("join game")
                stub = cs_pb2_grpc.CSStub(channel)
                stub.JoinPlayer(cs_pb2.CSReqJoinPlayer(
                    uid=UID,
                    name="player"+str(UID),
                    chips=1000,
                    ip=get_all_local_ips()[0],
                    port=int(PORT)
                ))
            elif user_input == "start":
                print("start game")
                stub = cs_pb2_grpc.CSStub(channel)
                stub.StartGameplay(cs_pb2.CSReqStartGameplay(uid=UID))
            elif user_input == "check":
                print("check card")
                stub = cs_pb2_grpc.CSStub(channel)
                stub.Check(cs_pb2.CSReqCheck(uid=UID))
            elif user_input == "call":
                print("call bet")
                stub = cs_pb2_grpc.CSStub(channel)
                stub.Call(cs_pb2.CSReqCall(uid=UID))
    except KeyboardInterrupt:
        print("keyboard interrupt")
    finally:
        print("client stop")
        
if __name__ == "__main__":
    UID = int(time.time())
    main()