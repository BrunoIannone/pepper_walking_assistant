import qi
import argparse
import sys
import time
import random
import math
import json
import os

from automaton.automaton import State, TimeoutState, FiniteStateAutomaton
from utils.limits import joint_limits
from utils.postures import default_posture, left_arm_raised, right_arm_raised
from graph.graph import Node, Graph
from graph.room_mapper import RoomMapper

# --------------------------------- Services --------------------------------- #

global as_service  # Animated Speech
global bm_service  # Behavior Manager
global ap_service  # Animation Player
global mo_service  # Motion
global me_service  # Memory
global to_service  # Touch
global na_service  # Navigation
# global sr_service # Speech Recognition

# ------------------------- User specific parameters ------------------------- #
global alevel       # Disablity level
global wtime        # Time to wait before asking if we need to cancel the procedure
global lang         # Language

# ----------------------------------- Modim ---------------------------------- #
global mws

# --------------------------------- Variables -------------------------------- #

# The robot is using either the left or the right hand
global hand_picked
hand_picked = 'Left'

# Finite state automata
global automaton

# Signals
global touch_subscriber  #, word_subscriber

# Current and target position
global coords
global current_pos
global current_target
global current_x, current_y
global at_goal
global node_index
at_goal = False
node_index = 0
current_x = 0
current_y = 0


# ---------------------------------- States ---------------------------------- #

class SteadyState(TimeoutState):

    def __init__(self, automaton, timeout=10):
        super(SteadyState, self).__init__('steady_state', automaton, timeout=timeout, timeout_event='time_elapsed')

    def on_enter(self):
        super(SteadyState, self).on_enter()
        print("[INFO] Entering Steady State")

        # Behavior

        perform_movement(joint_values=default_posture)
        print('[INFO] Resetting posture')

        """
        if alevel == DEAF:
            # Run modim interaction to show the relative message on tablet
            pass 
        elif alevel == BLIND:
        """
        global hand_picked
        sentence_key = "hold_hand_" + hand_picked.lower()
        animated_say(sentence_key)
        print('[INFO] Talking: ' + sentence_key)

        perform_movement(joint_values=left_arm_raised if hand_picked == 'Left' else right_arm_raised, speed=0.25)
        print("[INFO] Raising " + hand_picked.lower() + " hand")

    def on_event(self, event):
        super(SteadyState, self).on_event(event)
        if event == 'hand_touched':
            self.automaton.change_state('moving_state')
        elif event == 'time_elapsed':
            self.automaton.change_state('quit_state')


class MovingState(State):
    def __init__(self, automaton):
        super(MovingState, self).__init__('moving_state', automaton)

    def on_enter(self):
        super(MovingState, self).on_enter()
        print('[INFO] Entering Moving State')

        # Behavior
        global current_x, current_y
        global at_goal
        global node_index
        while not at_goal:
            print('[INFO] At goal status: {}'.format(at_goal))
            print('[INFO] Node index: {}'.format(node_index))
            print('[INFO] Current target: {}'.format(coords[node_index]))
            current_target_x, current_target_y = coords[node_index]
            theta = math.atan2(current_target_y - current_y, current_target_x - current_x)
            print('[INFO] Current theta: {}'.format(theta))
            print('[INFO] Moving to: ' + str(current_target_x) + ', ' + str(current_target_y))
            success = move_to(current_target_x, current_target_y, theta)
            print('[INFO] Success state for {}: {}'.format(node_index, success))
            if success:
                node_index += 1
            if node_index == len(coords):
                print('[INFO] Success in exit if')
                at_goal = True

        print('[INFO] Success Exited from while loop')


    def on_event(self, event):
        super(MovingState, self).on_event(event)
        if event == 'hand_released':
            stop_motion()
            self.automaton.change_state('ask_state')


class QuitState(State):

    def __init__(self, automaton):
        super(QuitState, self).__init__('quit_state', automaton)

    def on_enter(self):
        super(QuitState, self).on_enter()
        print('[INFO] Entering Quit State')

        # Go back to default position
        perform_movement(joint_values=default_posture)
        print('[INFO] Resetting posture')

        # Unsubscribe from signals
        # global touch_subscriber, word_subscriber, sr_service
        # sr_service.unsubscribe("pepper_walking_assistant_ASR")
        # word_subscriber.signal.disconnect()
        # touch_subscriber.signal.disconnect()

        print("[INFO] Done")


class HoldHandState(TimeoutState):

    def __init__(self, automaton, timeout=10):
        super(HoldHandState, self).__init__('hold_hand_state', automaton, timeout=timeout, timeout_event='time_elapsed')

    def on_enter(self):
        super(HoldHandState, self).on_enter()
        print('[INFO] Entering Hold Hand State')

        # Behavior
        sentence_key = "grab_hand_to_continue"
        animated_say(sentence_key)
        print('[INFO] Talking: Grab my hand to continue!')

    def on_event(self, event):
        super(HoldHandState, self).on_event(event)
        if event == 'hand_touched':
            self.automaton.change_state('moving_state')
        elif event == 'time_elapsed':
            self.automaton.change_state('quit_state')


class AskState(TimeoutState):

    def __init__(self, automaton, timeout=10):
        super(AskState, self).__init__('ask_state', automaton, timeout=timeout, timeout_event='steady_state')

    def on_enter(self):
        super(AskState, self).on_enter()
        print("[INFO] Entering Ask State")

        # Behavior
        sentence_key = "ask_cancel"
        animated_say(sentence_key)
        print('[INFO] Talking: Do you want to cancel?')

        # TODO remove user response simulation
        on_word_recognized(None)

    def on_event(self, event):
        super(AskState, self).on_event(event)
        if event == 'response_yes':
            self.automaton.change_state('quit_state')
        elif event == 'response_no':
            self.automaton.change_state('hold_hand_state')
        elif event == 'hand_touched':
            self.automaton.change_state('moving_state')
        elif event == 'time_elapsed':
            self.automaton.change_state('quit_state')


# ------------------------------ Utility methods ----------------------------- #

def animated_say(sentence_key):
    """
    Say something while contextually moving the head as you speak.
    The sentence_key and lang identify a sentence in a particular language. 
    """
    global as_service, lang
    configuration = {"bodyLanguageMode": "contextual"}
    sentence = lang.get(sentence_key, "[Missing translation for " + sentence_key + "]")
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


def move_to(x, y, theta):
    """
    Move the robot to the specified target position and orientation.

    This function uses ALNavigation.navigateTo for movement to (x, y) coordinates
    and ALMotion.moveTo for the final orientation adjustment.

    Parameters:
    x (float): Target X coordinate in meters (in FRAME_WORLD).
    y (float): Target Y coordinate in meters (in FRAME_WORLD).
    theta (float): Target orientation in radians (in FRAME_WORLD).

    Returns:
    bool: True if the robot successfully reached the target, False otherwise.

    Note:
    - The maximum distance for a single navigateTo call is 3 meters.
    - This function updates the global current_x and current_y variables.
    """
    global na_service, current_x, current_y, mo_service

    try:
        # Calculate relative movement
        delta_x = x - current_x
        delta_y = y - current_y

        # Use navigateTo for movement
        #success = na_service.navigateTo(delta_x, delta_y)
        mo_service.moveTo(delta_x, delta_y, theta)
        success=True

        if success:
            # Update current position if movement was successful
            current_x, current_y = x, y

            # Rotate to the desired orientation
            #mo_service.moveTo(0, 0, theta)

            print("[INFO] Moved to position: ({}, {}) with orientation {}".format(x, y, theta))
        else:
            print("[INFO] Navigation failed or was interrupted")

        return success
    except Exception as e:
        print("[ERROR] Failed to move: {}".format(e))
        return False


def stop_motion():
    """
    Stop the robot's motion and update the current location.

    This function uses ALMotion.stopMove() to halt the robot's movement
    and then updates the global current_x and current_y variables with
    the robot's final position.

    Note:
    - This function updates the global current_x and current_y variables.
    """
    global mo_service, me_service, current_x, current_y
    try:
        # Stop the robot
        mo_service.stopMove()

        # Get the current position
        robot_pose = mo_service.getRobotPosition(True)
        current_x, current_y = robot_pose[0], robot_pose[1]

        print("[INFO] Motion stopped. Current position: ({}, {})".format(current_x, current_y))
    except Exception as e:
        print("[ERROR] Failed to stop motion: {}".format(e))

def load_language(languages_path, language_code):
    """
    Load the translation file based on the selected language.
    """
    try:
        file_path = os.path.join(languages_path, language_code + '.json')
        with open(file_path, 'r') as file:
            return json.load(file)
    except:
        print("Error: Language file for " + file_path + " not found.")
        return {}
    
# --------------------------------- Callbacks -------------------------------- #

def on_hand_touch_change(value):
    """
    Callback function triggered when the hand touch event occurs.
    Dispatch the event to the automata.
    """
    global hand_picked, automaton
    print("[INFO] " + hand_picked + " hand touch value changed: " + str(value))
    if value == 0.0:
        automaton.on_event('hand_released')
    else:
        automaton.on_event('hand_touched')


def on_word_recognized(value):
    """
    Callback function triggered when a word is recognized.
    Dispatch the event to the automata.
    """

    """
    recognized_word = value[0] if value else ""
    print("[INFO] Recognized word: ", recognized_word)
    
    global automaton
    if recognized_word == "yes":
        automaton.on_event('response_yes')
    elif recognized_word == "no":
        automaton.on_event('response_no')
    else:
        print("[INFO] Response not recognized")
    """

    time.sleep(random.randint(2, 4))

    global automaton
    if random.random() > 0.5:
        print('[USER] Response: yes')
        automaton.on_event('response_yes')
    else:
        print('[USER] Response: no')
        automaton.on_event('response_no')


# ----------------------------------- Main ----------------------------------- #

def main():

    # ----------------------------- Argument parsing ----------------------------- #
    parser = argparse.ArgumentParser()
    parser.add_argument("--pip", type=str, default=os.environ['PEPPER_IP'],
                        help="Robot IP address.  On robot or Local Naoqi: use '127.0.0.1'.")
    parser.add_argument("--pport", type=int, default=9559,
                        help="Naoqi port number")
    parser.add_argument("--current_room", type=str, default="A",
                        help='ID of the room you are currently in')
    parser.add_argument("--target_room", type=str, default="D",
                        help='ID of the room to go to')
    parser.add_argument("--alevel", type=int, default=1,
                        help='Disability level. The higher it is, the more paths are available')
    parser.add_argument("--wtime", type=int, default=60,
                        help='Number of seconds to wait with the hand raised before canceling the procedure')
    parser.add_argument("--lang", type=str, default='en',
                        help='Language')

    args = parser.parse_args()
    pip = args.pip
    pport = args.pport

    # Starting application
    try:
        connection_url = "tcp://" + pip + ":" + str(pport)
        app = qi.Application(["Memory Read", "--qi-url=" + connection_url])
    except RuntimeError:
        print("Can't connect to Naoqi at ip \"" + pip + "\" on port " + str(pport) + ".\n"
                                                                                     "Please check your script arguments. Run with -h option for help.")
        sys.exit(1)
    app.start()
    session = app.session

    # ------------------------- User specific parameters ------------------------- #
    global alevel, wtime, lang
    alevel = args.alevel
    wtime = args.wtime

    lang = load_language('src/config/languages', args.lang)
    print("[INFO] Selected vocabulary: " + args.lang)

    # -------------------------- Initialize the services ------------------------- #
    global as_service, bm_service, ap_service, mo_service, me_service, na_service  #, sr_service
    as_service = session.service("ALAnimatedSpeech")
    bm_service = session.service("ALBehaviorManager")
    ap_service = session.service("ALAnimationPlayer")
    mo_service = session.service("ALMotion")
    me_service = session.service("ALMemory")

    #na_service = session.service("ALNavigation")
    # sr_service = session.service("ALSpeechRecognition")

    # ---------------------------- Start modim client ---------------------------- #
    global mws
    # mws = ModimWSClient()
    # mws.setDemoPathAuto(__file__) # Better leave this here

    # --------------------------- Graph initialization --------------------------- #
    graph = Graph.static_load('src/config/graph.txt')
    distance, path = graph.shortest_path(args.current_room, args.target_room, args.alevel)
    print("[INFO] Current room       : " + str(args.current_room))
    print("[INFO] Target room        : " + str(args.target_room))
    print("[INFO] Accessibility level: " + str(args.alevel))
    print("[INFO] Path               : " + str(path))

    # Take the coordinates for each node
    global coords
    room_mapper = RoomMapper.static_load('src/config/coords.txt')
    print("[INFO] Rooms coordinates  : ")
    for name, (x, y) in room_mapper.rooms.items():
        print("[INFO] \t" + name + ": ( " + str(x) + ", " + str(y) + ")")
    coords = [room_mapper[node] for node in path]

    # Use the first node to establish which hand to raise
    global hand_picked
    first_coords = coords[0]
    first_x, _ = first_coords
    hand_picked = 'Right' if first_x < 0 else 'Left'
    print("[INFO] Selected " + hand_picked.lower() + " hand to raise")

    # --------------------------------- Automaton -------------------------------- #
    global automaton
    automaton = FiniteStateAutomaton()

    steady_state = SteadyState(automaton, timeout=args.wtime)
    moving_state = MovingState(automaton)
    ask_state = AskState(automaton, timeout=args.wtime)
    hold_hand_state = HoldHandState(automaton, timeout=args.wtime)
    quit_state = QuitState(automaton)

    automaton.add_state(steady_state)
    automaton.add_state(moving_state)
    automaton.add_state(ask_state)
    automaton.add_state(hold_hand_state)
    automaton.add_state(quit_state)

    automaton.start('steady_state')

    # ------------ Connect the pepper event callbacks to the automaton ----------- #
    global touch_subscriber  #, word_subscriber

    touch_event = "Hand" + hand_picked + "BackTouched"
    touch_subscriber = me_service.subscriber(touch_event)
    touch_subscriber.signal.connect(on_hand_touch_change)

    """
    sr_service.setLanguage("English")
    sr_service.setVocabulary(["yes", "no"], False)
    sr_service.subscribe("pepper_walking_assistant_ASR")  # Start the speech recognition engine with user pepper_walking_assistant_ASR
    word_subscriber = me_service.subscriber("WordRecognized") # Subscribe to event WordRecognized
    word_subscriber.signal.connect(on_word_recognized)
    """

    # ------------------------------------ Run ----------------------------------- #

    # Program stays at this point until we stop it
    app.run()


if __name__ == "__main__":
    main()
