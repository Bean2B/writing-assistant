# Continuing reader sessions

Use three independent readers with different tastes. 人物读者 tends to remember relationships and emotional choices. 行动读者 follows decisions, physical action and whether a character has learned to do something. 氛围读者 follows atmosphere, ambiguity and the questions a scene leaves open. Each may dislike a chapter, stop or change their mind. These preferences are private session setup, never a checklist in the reading prompt.

For each reader, look up the existing session with `reader NAME`. Resume the same session when possible. If a session must be created, store the actual handle using `reader NAME --handle HANDLE`. A replacement can receive its own earlier raw reactions, retrieved with `reviews N --revision R --reader NAME`. Record the session change with the trial if it affects interpretation.

Prepare each reader's copy using `packet N --revision R --reader NAME`. Send only its decoded `text` and the same neutral question to that reader. Keep chapter order and manuscript bytes identical across readers. Preserve chronological order and a common variant order for comparisons. Never give readers access to the book database, test assessments, other readers' replies or author notes. Use the host's independent sessions and delivery tools. The CLI prepares and records packets locally.

A suitable prompt is “读完这章，你在意谁，期待什么，还想接着读吗？如果停下了，记下停在哪里。” Keep the original reply including uncertainty, disagreement and stopping points. Record it with `feedback --packet ID --sha256 SHA --file reply.md`. A prepared packet demonstrates local preparation. Record a reading outcome only after receiving the actual session's reply. Report unavailable sessions or missing replies explicitly.

Let each reader form an opinion before any discussion. The author weighs replies against the intended reading experience, including room for different interpretations. A unanimous response is unnecessary for a creative decision.
