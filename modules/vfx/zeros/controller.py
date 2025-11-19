from pythonosc import udp_client
import logging

logger = logging.getLogger(__name__)

class ZerOSController:
    def __init__(self, board_ip, port=8830):
        logger.debug(f"ZerOSController.__init__ called with board_ip={board_ip}, port={port}")
        self.board_ip = board_ip
        self.port = port
        logger.debug(f"Attempting to initialize ZerOSController for IP {self.board_ip} on port {self.port}")
        try:
            self.client = udp_client.SimpleUDPClient(self.board_ip, self.port)
            logger.info(f"Initialized OSC client for ZerOS board at {self.board_ip}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to initialize OSC client: {e}")
            self.client = None

    def execute_action(self, action):
        logger.debug(f"ZerOSController.execute_action called with action: {action.to_dict() if hasattr(action, 'to_dict') else action}")
        if not self.client:
            logger.error("ZerOS OSC client not initialized. Cannot execute action.")
            return

        if action.osc_address:
            address = action.osc_address
            logger.info(f"Executing custom ZerOS OSC action: Address: {address}")
            try:
                self.client.send_message(address, None)
                logger.info(f"Sent OSC message to {address} with value None")
            except Exception as e:
                logger.error(f"An unexpected error occurred during custom ZerOS OSC action: {e}")
            return

        if action.command == "release" and action.release_id:
            target_id = action.release_id
        else:
            target_id = action.preset_id
        target_type = action.target_type or 'playback'
        command = action.command or 'go'

        logger.debug(f"Received lighting action: {action}")
        logger.debug(f"Target ID: {target_id}, Target Type: {target_type}, Command: {command}")
        logger.info(f"Executing ZerOS action: Target: {target_type} {target_id}, Command: {command}")

        try:
            # ZerOS OSC command format used here: /zeros/<target_type>/<command>/<target_id>
            # If the target is a cue and no ID was provided, default to cue 1
            if target_type == 'cue' and (target_id is None or str(target_id).strip() == ''):
                logger.debug("No cue ID provided; defaulting to cue 1")
                target_id_num = 1
            else:
                target_id_num = int(target_id)

            address = f"/zeros/{target_type}/{command}/{target_id_num}"
            
            logger.debug(f"Constructed OSC address: {address}")
            self.client.send_message(address, None)
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
            action1 = LightingAction(preset_id=15)
            zeros_controller.execute_action(action1)
            
            time.sleep(3)
            
            # Example: Fire cue 14 (stage)
            action2 = LightingAction(preset_id=14)
            zeros_controller.execute_action(action2)
