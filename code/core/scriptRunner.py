import scripts.dummyScript as dummyScript

scripts = {
    'dummyScript': dummyScript
}

def runScript(popName):
    return scripts[popName].main()


