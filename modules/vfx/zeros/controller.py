from pythonosc import udp_client
import logging

logger = logging.getLogger(__name__)

class ZerOSController:
    def __init__(self, board_ip, port=8000):
        self.board_ip = board_ip
        self.port = port
        try:
            self.client = udp_client.SimpleUDPClient(self.board_ip, self.port)
            logger.info(f"Initialized OSC client for ZerOS board at {self.board_ip}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to initialize OSC client: {e}")
            self.client = None

    def execute_action(self, action):
        if not self.client:
            logger.error("ZerOS OSC client not initialized. Cannot execute action.")
            return

        target_id = action.preset_id
        target_type = action.target_type or 'cue'
        command = action.command or 'fire'
        
        logger.info(f"Executing ZerOS action: Target: {target_type} {target_id}, Command: {command}")

        try:
            # ZerOS OSC command format: /zeros/<target_type>/<target_id>/<command>
            target_id_num = int(target_id)
            address = f"/zeros/{target_type}/{command}/{target_id_num}"
            
            self.client.send_message(address, 1.0) # Sending a float value of 1.0 to fire/go
            logger.info(f"Sent OSC message to {address}")

        except (ValueError, TypeError):
            logger.error(f"Invalid target_id for ZerOS: {target_id}. Must be an integer.")
        except Exception as e:
            logger.error(f"An unexpected error occurred during ZerOS OSC action: {e}")

if __name__ == '__main__':
    # Example usage for testing
    import os
    from models.actions import LightingAction
    import time

    ZEROS_IP = os.environ.get("ZEROS_IP")
    ZEROS_PORT = int(os.environ.get("ZEROS_PORT", 8000))

    if not ZEROS_IP:
        print("Please set the ZEROS_IP environment variable.")
    else:
        logging.basicConfig(level=logging.INFO)
        zeros_controller = ZerOSController(ZEROS_IP, ZEROS_PORT)

        if zeros_controller.client:
            print("ZerOS controller initialized.")
            
            # Example: Fire cue 13 (standby)
            action1 = LightingAction(preset_id=13)
            zeros_controller.execute_action(action1)
            
            time.sleep(3)
            
            # Example: Fire cue 14 (stage)
            action2 = LightingAction(preset_id=14)
            zeros_controller.execute_action(action2)
