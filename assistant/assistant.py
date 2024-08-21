import qi
import argparse
import sys
import time
import random
import math
import os

from automata import State, TimeoutState, FiniteStateAutomaton


# ------------------------- Joint values for postures ------------------------ #

joint_limits = {
    'HeadYaw': (-2.0857, 2.0857),
    'HeadPitch': (-0.7068, 0.6371),
    'LShoulderPitch': (-2.0857, 2.0857),
    'LShoulderRoll': (0.0087, 1.5620),
    'LElbowYaw': (-2.0857, 2.0857),
    'LElbowRoll': (-1.5620, -0.0087),
    'LWristYaw': (-1.8239, 1.8239),
    'RShoulderPitch': (-2.0857, 2.0857),
    'RShoulderRoll': (-1.5620, -0.0087),
    'RElbowYaw': (-2.0857, 2.0857),
    'RElbowRoll': (0.0087,1.5620),
    'RWristYaw': (-1.8239, 1.8239)
}

left_arm_raised = {
    'LShoulderRoll': 1.5620,
    'LElbowYaw': -1.5,
    'LElbowRoll': -1.5,
    'LWristYaw': -0.5
}

right_arm_raised = {
    'RShoulderRoll': -1.5620,
    'RElbowYaw': 1.5,
    'RElbowRoll': 1.5,
    'RWristYaw': 0.5,
}

default_posture = {
    'HeadYaw': 0.0,
    'HeadPitch': -0.2,
    'LShoulderPitch': 1.5,
    'LShoulderRoll': 0.1,
    'LElbowYaw': -1.2,
    'LElbowRoll': -0.5,
    'LWristYaw': 0.0,
    'RShoulderPitch': 1.6,
    'RShoulderRoll': -0.1,
    'RElbowYaw': 1.2,
    'RElbowRoll': 0.5,
    'RWristYaw': 0.0
}


# --------------------------------- Services --------------------------------- #

global as_service # Animated Speech
global bm_service # Behavior Manager
global ap_service # Animation Player
global mo_service # Motion
global me_service # Memory
global to_service # Touch
global sr_service # Speech Recognition

# --------------------------------- Variables -------------------------------- #

# The robot is using either the left or the right hand
global hand_picked
hand_picked = 'Left'

# State to track if the hand is currently touched or not 
global hand_touch_status
hand_touch_stastus = 0.0

# Finite state automata
global automaton

# ---------------------------------- States ---------------------------------- #

class SteadyState(State):

    def __init__(self, automaton) -> None:
        super().__init__('steady_state', automaton)

    def on_enter(self):
        super().on_enter()
        print("[INFO] Entering Steady State")


    def on_event(self, event):
        super().on_event(event)
        if event == 'hand_touched':
            self.automaton.change_state('moving_state')

# ------------------------------ Utility methods ----------------------------- #

def asay(sentence):
    """
    Say something while contextually moving the head as you speak 
    """
    global as_service 
    configuration = {"bodyLanguageMode":"contextual"}
    as_service.say(sentence, configuration)


def perform_animation(animation, _async=True):
    """
    Perform a predefined animation. The animation should be visible by the behavior_manager 
    among the installed behaviors, otherwise it is silently discarded 
    """
    global bm_service, ap_service
    behaviors = bm_service.getInstalledBehaviors()
    
    if animation in behaviors:    
        ap_service.run(animation, _async=_async)


def perform_movement(joint_values, speed=1.0, _async=True):
    """
    Perform the motion specified by the provided joint values. Joint values 
    should be in the allowed range, otherwise the value is silently discarded
    """
    global mo_service
    mo_service.setStiffnesses('Body', 1.0)

    for joint_name, joint_value in joint_values.items():
        if joint_limits[joint_name][0] <= joint_value <= joint_limits[joint_name][1]:
            mo_service.setAngles(joint_name, joint_value, speed, _async=_async)

def procedure(target_coords):

    """
    global hand_picked

    # Unpack the target coordinates
    x, y = target_coords

    # Establish if the robot has to move left or right
    if x > 0:
        # The robot has to move right, raise left hand
        hand_picked = "Left"
    else:
        # The robot has to move left, raise right hand
        hand_picked = "Right"
    print("[INFO] " + hand_picked + " selected")

    # Raise the respective arm (async)
    perform_movement(joint_values=left_arm_raised if hand_picked == 'Left' else right_arm_raised, speed=0.25)

    # Give instructions to the user while the hand is raising
    asay("Hold my " + hand_picked.lower() + " hand and I'll guide you there!")

    # Wait for the touch or timeout
    time.sleep(20)  # Giving the user 20 seconds to touch the hand
    
    if hand_touch_status == 0.0:
        print("[INFO] No touch detected.")
        asay("No touch detected.")

    # Return to default posture
    perform_movement(default_posture)
    """

    pass

# --------------------------------- Callbacks -------------------------------- #

def on_hand_touch_change(value):
    """
    Callback function triggered when the hand touch event occurs.
    Dispatch the event to the automata
    """
    global hand_picked, automaton
    print("[INFO] " + hand_picked + " hand touch value changed: " + str(value))
    if value == 0.0:
        automaton.on_event('hand_touched')
    else:
        automaton.on_event('hand_released')

# ----------------------------------- Main ----------------------------------- #

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pip", type=str, default=os.environ['PEPPER_IP'],
                        help="Robot IP address.  On robot or Local Naoqi: use '127.0.0.1'.")
    parser.add_argument("--pport", type=int, default=9559,
                        help="Naoqi port number")
    parser.add_argument("--coords", type=float, nargs=2, metavar=('X', 'Y'), default=[1.0, 1.0], 
                        help="Target coordinates")
    args = parser.parse_args()
    pip = args.pip
    pport = args.pport

    # Starting application
    try:
        connection_url = "tcp://" + pip + ":" + str(pport)
        app = qi.Application(["Memory Read", "--qi-url=" + connection_url ])
    except RuntimeError:
        print ("Can't connect to Naoqi at ip \"" + pip + "\" on port " + str(pport) +".\n"
               "Please check your script arguments. Run with -h option for help.")
        sys.exit(1)
    app.start()
    session = app.session

    # Initialize the services
    global as_service, bm_service, ap_service, mo_service, me_service, sr_service
    as_service = session.service("ALAnimatedSpeech")
    bm_service = session.service("ALBehaviorManager")
    ap_service = session.service("ALAnimationPlayer")
    mo_service = session.service("ALMotion")
    me_service = session.service("ALMemory")
    sr_service = session.service("ALSpeechRecognition")

    # Establish which hand to use
    global hand_picked
    global x, y
    x, y = args.coords
    print("[INFO] Target position: " + x + ", " + y)

    # Create the automata
    automaton = FiniteStateAutomaton()

    steady_state = SteadyState(automaton, hand=hand_picker)
    moving_state = MovingState(automaton)
    goal_state = GoalState(automaton)
    ask_state = AskState(automaton, timeout=10)
    ask2_state = Ask2State(automaton, timeout=10)

    automaton.add_state(steady_state)
    automaton.add_state(moving_state)
    automaton.add_state(goal_state)
    automaton.add_state(ask_state)
    automaton.add_state(ask2_state)

    automaton.set_initial_state('steady_state')

    # Connect the pepper event callbacks to the automata
    touch_event = "Hand" + hand_picked + "BackTouched"
    subscriber = me_service.subscriber(touch_event)
    subscriber.signal.connect(on_hand_touch_change)

    # Program stays at this point until we stop it
    app.run()

    print("Finished")


if __name__ == "__main__":
    main()
