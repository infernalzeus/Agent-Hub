"""The practice yard (R6): a safe place for the Hub to practise PC tasks thousands of times.

A pretend app stands in for a real one. It speaks the same language the real desktop agent reads (the control tree, the Windows
media session, click/type/key), so the REAL `desktop_agent.attempt` runs against it unchanged and its verdict can be checked
against the pretend app's own state, which is exact. Nothing here touches the real desktop, the network, the Hub's settings or
its learning log: the yard only writes its own report under STATE/yard/ when asked.

    world.py     pretend apps (families of layouts, label vocabularies) and their exact truth
    learner.py   what the policy sees (the same prompt a model gets), its actions, and a small actor-critic that learns from returns
    practice.py  run episodes, train, evaluate against baselines on layouts and labels it never trained on, write the report
    api.py       GET /api/yard/status (last report), POST /api/yard/practice (explicit, bounded)

Run it from a terminal:  python -m hub.yard.practice --episodes 4000
"""
