def scenario_1_signature():
    return "Spoofing evidence found in sip-cli"

def scenario_2_signature():
    return "DoS success: freeswitch container status"

def scenario_3_signature():
    return "Attack success: kamailio status"


def scenario_4_signature():
    return "RTP injection detected"

def scenario_5_signature():
    return "bypass succeeded"

def scenario_6_signature():
    return "RCE proof verified"

def scenario_7_signature():
    return "NoSQLi bypass verified"

def scenario_8_signature():
    return "XSS vulnerable surface"

def scenario_9_signature():
    return "Audio capture storage verified"

scenario_signaures = {
    1: scenario_1_signature(),
    2: scenario_2_signature(),
    3: scenario_3_signature(),
    4: scenario_4_signature(),  
    5: scenario_5_signature(),
    6: scenario_6_signature(),
    7: scenario_7_signature(),
    8: scenario_8_signature(),
    9: scenario_9_signature(),
}



def get_attack_success_signature(scenario_id: int) -> str:
    """Get the expected signature string that indicates attack success for a given scenario."""
    return scenario_signaures.get(scenario_id, "Unknown scenario")


def check_signature_in_output(scenario_id: int, output: str) -> bool:
    """Check if the expected attack success signature is present in the given output."""
    signature = get_attack_success_signature(scenario_id)
    return signature in output