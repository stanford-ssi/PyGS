import scripts.dummyScript as dummyScript

scripts = {
    'dummyScript': dummyScript
}

def runScript(popModule):
    return scripts['popModule'].main()


