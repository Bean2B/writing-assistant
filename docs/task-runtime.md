# Durable tasks and reader sessions

The book stores the task plan, its digest, one dispatch attempt, verified response and materialized output. A task writes an unadopted draft or attaches an exact reader reply to an issued manuscript packet. Each completed output also gets an immutable Creative Record with its origin, model, target and plan digest. A workflow coordinates ordered chapters and the same readers across those chapters.

## Run a local bridge

From the checkout, choose the local book and explicitly select an executable that speaks the JSON protocol below. The supplied bridge supports Codex through the local CLI account, and DeepSeek, Claude and Gemini through their own HTTPS APIs. Use the provider's current model identifier. The model and effort strings sent reflect the configured request. The provider determines availability.

```sh
wa=./scripts/writing-assistant
book='books/创作作品/渡灯'
runner=./scripts/writing-assistant-provider
"$wa" --book "$book" task prepare-write opening 1 --goal '写开篇第一章' \
  --provider deepseek --model deepseek-flash --effort high --runner "$runner"
"$wa" --book "$book" task inspect opening
"$wa" --book "$book" task execute opening --expected-plan-sha256 DIGEST --runner "$runner"
"$wa" --book "$book" task output opening
```

Preparation freezes the book's Direct or Lotus settings, previous chapter, active author notes, selected records, model settings and local runner digest. Use repeated `--material REF` arguments to select Creative Records. To consume an explicitly curated packet, save the output of `prepare REQUEST --target N` and pass `task prepare-write ID N --prepared FILE` in place of `--goal`. The task reconstructs and compares the complete packet against this book, including its chapter references, record bytes, mode, target and digest. Its input includes only those selected materials. A changed writing mode or target at dispatch produces a conflict. Reader tasks take their text from fixed reader packets.

Inspection reports the requested provider, model, effort, transport, chapter, role and state. Add `--include-context` to inspect the frozen plan and selected bytes locally before dispatch.

New writer requests advertise `output_format: manuscript-and-card/1`. The bundled bridge requests manuscript text and a separate [chapter card](world-and-records.md#chapter-dossiers) in the same generation. A desktop or custom adapter can include the object as `chapter_card` alongside `text` in its response. Only the text enters manuscript reads and reader packets. A prose-only adapter leaves the card pending for the author.

The local bridge reads the selected API credential (`DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`) only when that provider is executed. Codex uses an ephemeral CLI process in a temporary directory with user configuration ignored, read-only sandboxing and tool features disabled. The bridge omits API keys from its Codex child environment. The supplied runner has no network or account checks at preparation. Actual API calls can incur charges. Each request is text-only.

DeepSeek uses Chat Completions with thinking enabled and the requested effort. [DeepSeek thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/)

Claude uses the Messages API with `output_config.effort`. [Claude effort settings](https://platform.claude.com/docs/en/build-with-claude/effort)

Gemini uses generateContent with `generationConfig.thinkingConfig.thinkingLevel`. The selected model needs to support that reasoning control. [Gemini thinking](https://ai.google.dev/gemini-api/docs/thinking)

## Reader and desktop handoffs

Register a real native host handle with `reader NAME --handle HANDLE`. Issue `packet N --revision R --reader NAME`, then `task prepare-review ID --packet PACKET --provider PROVIDER --model MODEL`. Omit `--runner` to select the desktop handoff. `task execute ID --expected-plan-sha256 DIGEST` returns a single `desktop_request` for the host coordinator. The coordinator routes its `input.text` and neutral `input.prompt` to the named session and collects the response. Session metadata remains with the coordinator. Ongoing desktop delivery requires that host's own session control. These commands do not edit desktop configuration.

For the supplied stateless CLI/API bridge, use a book-managed reader handle such as `local:deepseek:ahe`. Its task includes that reader's stated taste and their own prior responses from the same book and handle. This reconstructs a reader's reading history across calls. It does not claim access to an existing vendor desktop conversation. Other readers' replies and author-only notes stay outside reader packets.

A local adapter receives one UTF-8 JSON request on stdin and emits one JSON response on stdout. A desktop coordinator saves the same response format and runs `task receive ID --expected-plan-sha256 DIGEST --file reply.json`. Echo the exact identity fields from the handoff. `session` identifies the responding host session or book-managed reader. `text` holds the original answer, including newlines. Usage can be null or a map of observed nonnegative integer token counts.

```json
{"format":"writing-assistant/task-response/1","task_id":"ID","attempt":"ATTEMPT","plan_sha256":"DIGEST","provider":"deepseek","model":"MODEL","session":"HANDLE","text":"原话","usage":null}
```

## Advance a workflow

Register the readers first. `workflow create ID --goal TEXT --start N --chapters COUNT --readers 人物读者 行动读者 氛围读者 --writer-provider PROVIDER --writer-model MODEL --reader-provider PROVIDER --reader-model MODEL` fixes their order and session bindings. Use `--writer-runner PATH` and `--reader-runner PATH` for local adapters. The writer and reader can use different profiles. Use `workflow next ID --expected-plan-sha256 DIGEST` to return the current task or prepare the next. Run the returned task explicitly, then advance again. Each reader receives the same saved revision. A changed prior revision, bound reader session or project mode can block advancement. Concurrent or repeated advancement resolves to the same outstanding task.

## Recovery and evidence

A POSIX supervisor process holds the book's advisory lock while running the adapter. The book allows one outstanding dispatch. It records its claim before launch. The supervisor writes an atomic private result in the book's `.writing-tasks/` directory so a new coordinator can recover after the original coordinator exits. Keep this directory with its book during an in-flight attempt. Keep books quiescent before moving or backing them up.

Inspect `state` in each returned receipt. Execute, receive and recover emit the structured result and exit with code 2 for uncertain delivery or materialization conflict. Inspection of the same state succeeds. `completed` confirms response capture and local output materialization. A changed target can leave the task `captured` with `materialization_conflict`; `task output` retrieves the preserved bytes. `task recover ID --expected-plan-sha256 DIGEST` reuses a saved result. Reserved tasks never automatically launch again. A failed, incomplete or timed-out adapter response produces `uncertain` and a bounded fault code. Token usage remains null when unreported. A local exit cannot establish a remote provider's call count or cancellation.

Recovery of an outstanding desktop envelope returns its original attempt identity. The coordinator should inspect the destination session before considering delivery. If the user closes an unresolved handoff, `task close-uncertain ID --expected-plan-sha256 DIGEST` records that outcome and releases capacity. Live credential validity, actual desktop integration and literary quality require separate observations.

Run `python3 -m unittest discover -s tests -p 'test_tasks*.py' -v` for disposable-book tests. They launch local synthetic workers, interrupt the coordinator, exercise two chapters with three distinct readers, and use offline fixtures for the provider protocols.
