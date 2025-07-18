import grpc

import os
import sys
# 添加父目录的父目录到系统路径 (指向 Card/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time

from proto import cs_pb2
from proto import cs_pb2_grpc

IP = "111.229.201.75"
UID = 0

def show(res: cs_pb2.CSResHeartbeat):
    print(f"gameplay: {res}")

def main():
    try:
        channel = grpc.insecure_channel("localhost:50051")
        stub = cs_pb2_grpc.CSStub(channel)
        while True:
            # 用心跳包拿一次当前最新信息
            stub = cs_pb2_grpc.CSStub(channel)
            res = stub.Heartbeat(cs_pb2.CSReqHeartbeat(uid=UID))
            show(res)
            user_input = input("> ")
            if user_input in ["exit", "quit"]:
                print("client stop")
                break
            elif user_input == "join":
                print("join game")
                stub = cs_pb2_grpc.CSStub(channel)
                stub.JoinPlayer(cs_pb2.CSReqJoinPlayer(uid=UID,name="player"+str(UID),chips=1000))
            elif user_input == "start":
                print("start game")
                stub = cs_pb2_grpc.CSStub(channel)
                stub.StartGameplay(cs_pb2.CSReqStartGameplay(uid=UID))
    except KeyboardInterrupt:
        print("keyboard interrupt")
    finally:
        print("client stop")
        
if __name__ == "__main__":
    UID = int(time.time())
    main()