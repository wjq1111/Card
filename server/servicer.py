from proto import cs_pb2
from proto import cs_pb2_grpc

from gameplay import Gameplay

class CSServicer(cs_pb2_grpc.CSServicer):
    def __init__(self, gameplay: Gameplay):
        self.gameplay = gameplay
    
    def JoinPlayer(self, request: cs_pb2.CSReqJoinPlayer, context):
        self.gameplay.join_player(request.uid, request.name, request.chips, request.ip, request.port)
        self.gameplay.sync_gameplay()
        return cs_pb2.CSResJoinPlayer()
    
    def StartGameplay(self, request: cs_pb2.CSReqStartGameplay, context):
        self.gameplay.set_start_state()
        self.gameplay.sync_gameplay()
        return cs_pb2.CSResStartGameplay()
    
    def Call(self, request, context):
        self.gameplay.player_call(request.uid)
        return cs_pb2.CSResCall()
    
    def Check(self, request, context):
        self.gameplay.player_check(request.uid)
        return cs_pb2.CSResCheck()
