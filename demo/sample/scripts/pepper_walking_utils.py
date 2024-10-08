import os
class PepperWalkingUtils():
    def __init__(self):
        self.running = True

    def recognizedUser(self):
        return True
 
    def actionsPath(self):
        return os.path.join(os.path.dirname(os.path.realpath(__file__ )),"../actions/")
    
    def createCustomGreeting(self, user_name,disability):
        with open(os.path.join(self.actionsPath(),"custom_greeting"), "w") as file:
        
            if disability == "blind": #Blind
                contenuto = """IMAGE
<*, *, *, *>:  img/hello.png
----
TEXT
<*,*,it,*>: Accogliendo l'utente... {0}
<*,*,*,*>:  Welcoming the user... {0}
----
TTS
<*,*,it,*>: Ciao! Benvenuto {0}
<*,*,*,*>:  Hello! Welcome {0}
----""".format(user_name)
                
            else:                     #Deaf
                contenuto = """IMAGE
<*, *, *, *>:  img/hello.png
----
TEXT
<*,*,it,*>: Benvenuto {0}
<*,*,*,*>:  Welcome {0}
----
GESTURE
<*,*,*,*>: animations/Stand/Gestures/Hey_1
----""".format((user_name))
                
            file.write(contenuto)

    def checkStatus(self):
        status = None
        with open("/home/robot/playground/outcome.txt", "r") as file:
            status = file.readline().strip()
        return str(status).strip()

