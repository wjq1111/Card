import grpc
from proto import cs_pb2
from proto import cs_pb2_grpc

class SCServicer(cs_pb2_grpc.SCServicer):
    def __init__(self):
        super().__init__()
        
    def SyncGameplay(self, request: cs_pb2.CSReqSyncGameplay, context):
        print(f"recv sync {request.uid} gameplay {request.gameplay}")
        return cs_pb2.CSResSyncGameplay()