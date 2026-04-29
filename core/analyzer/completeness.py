def check_answer(answer):
    if not answer.strip():
        return "blank"
    if len(answer.split()) < 20:
        return "weak"
    return "ok"