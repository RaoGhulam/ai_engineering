# Assignment 02: Rubik's Cube Race

**Rao Ghulam Mohiuddin · 23K-0001** · AI Engineering

In this assignment I built a Rubik's Cube game where AI models solve the same scrambled 3×3 cube
one move at a time through OpenRouter. I wanted to test whether fast "System-1" decision models
can beat a frontier LLM that spends longer thinking. For each model I measured the time per move,
the total time, whether it solved the cube, and how many moves it used compared with the true
shortest solution.

My final results slide is in [`results_slide.html`](results_slide.html) and opens directly in a browser.

## How to run it

```bash
pip install -r requirements.txt
cp .env.example .env        # put the OpenRouter key in .env
python -m uvicorn app:app --app-dir backend --port 8000
```

Then open <http://localhost:8000>. The API key is read only by the backend
(`backend/config.py`) and is never sent to the browser. `.env` is in `.gitignore`.

The page has two modes:
- **Run benchmark** sends real OpenRouter requests and shows each move live.
- **Replay recorded run** plays back my saved run from `data/results.json` without calling the API.
  I used this for the screen recording.

To regenerate the slide: `python backend/make_slide.py --name "Rao Ghulam Mohiuddin" --roll 23K-0001`

## How I built it

| Part | What I did | File |
|---|---|---|
| Cube engine | I store the cube as a 54-character facelet string (URFDLB order). I generate all 18 moves by rotating 3D sticker positions instead of typing permutation tables by hand. I checked the engine against the standard Kociemba reference strings and known move orders, for example (R U) repeated 105 times returns to solved. | `backend/cube.py`, `tests/test_cube.py` |
| Shortest solution | Bidirectional breadth-first search finds the exact shortest solution, which I use for the optimality gap. | `backend/solver.py` |
| Model adapters | The three decision models use the Decisions API with a `choice` question whose options are the 18 moves. Opus uses chat completions with a JSON schema that only allows `{"move": "<one of 18>"}`. Both return a move in the same format. | `backend/adapters.py` |
| Benchmark runner | Every model gets the same puzzles, rules, timeout and retry policy. | `backend/benchmark.py` |
| Call counter | Every request is counted in `data/api_call_ledger.json` before it is sent, and the runner refuses to start if the worst case would pass the cap. My first run was capped at 67 calls. | `backend/budget.py` |
| Interface | Cubes side by side, the current move, move history with times, solved or move-limit status, a stats dashboard and a results slide. | `frontend/index.html` |

### Rules I used for every model

- **State given to the model:** the 54-character cube string, a drawn net of the cube, the last 5 moves, moves made and moves remaining.
- **Allowed actions:** the 18 standard moves (`U U' U2 R … B2`), each with the same description.
- **Checking answers:** I validate every reply before applying it. Broken, invalid or refused replies are logged as invalid outputs and use up a turn. I never guess a move from a bad reply.
- **Timeout and retries:** 180 s per request (a real wall-clock limit) and no retries. If a model returns a 4xx error, its trial stops so the same error doesn't burn more calls.
- **Puzzles:** 5 puzzles from seed 2026. Each is a 4-move scramble whose shortest solution is exactly 4 moves, which I confirmed with the search.
- **Move limit:** 30 moves, as the assignment specifies. Reaching 30 without solving counts as a failure.

```bash
python backend/benchmark.py --dry-run                 # show the puzzles, no API calls
python backend/benchmark.py --models jev luna clef    # run selected models
python backend/benchmark.py --models opus --append    # add a model to the same puzzles
python tests/test_cube.py                             # engine and search tests
```

## My two runs

**Run 1 (67-call cap).** At first I had to stay within 67 API calls, so I used 3 puzzles and a
5-move limit. Every model solved 0 of 3. Those results are kept in `data/results_limit5.json`.

**Run 2 (final, the one reported below).** Once the cap was lifted, I reran with the
assignment's 30-move limit on 5 puzzles. P1–P3 are the same puzzles as run 1. This run made
455 API calls.

### The frontier LLM

I couldn't get a frontier LLM result:

| Model | What happened |
|---|---|
| `anthropic/claude-opus-5.5` | HTTP 402: my OpenRouter credit couldn't cover a single request |
| `anthropic/claude-sonnet-5.5` | HTTP 400: reasoning is mandatory for this model, and my credit couldn't cover it |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | Thought for 500 s, used all 16,000 output tokens and never gave a move |
| `google/gemma-4-26b-a4b-it:free` | HTTP 429 (free tier rate-limited) in both runs, so it never made a move |

Two problems I found and fixed along the way:
- My runner originally kept going after HTTP 429, so Gemma used 15 calls in run 1 with no result. Now any 4xx stops the trial after one call.
- My first timeout didn't work: OpenRouter sends keep-alive bytes while a model thinks, so the HTTP library's read timeout never fired. I changed it to a real wall-clock deadline.

With credit, `python backend/benchmark.py --models opus --append` adds Opus to the same five puzzles.

## Results (run 2: 5 puzzles, 30-move limit)

| Model | Avg time per move | Total time (5 puzzles) | Total moves | Invalid outputs | Solved | Success rate | Optimality gap |
|---|---|---|---|---|---|---|---|
| Jev 1.13 (`typesafe/jev-1.13`) | **0.782 s** | **125.0 s** | 150 | 0 | 0/5 | 0% | n/a |
| GPT-6 Luna Decisions (`openai/gpt-6-luna-decisions`) | 1.405 s | 219.0 s | 0 | 150 (all refused) | 0/5 | 0% | n/a |
| Cloudflare Clef (`cloudflare/clef`) | 1.129 s | 178.2 s | 150 | 0 | 0/5 | 0% | n/a |
| Gemma 4 26B free (`google/gemma-4-26b-a4b-it:free`) | — | — | 0 | 5 (HTTP 429) | 0/5 | 0% (rate-limited) | n/a |
| Claude Opus 5.5 (`anthropic/claude-opus-5.5`) | not run (no credit) | | | | | | |

The shortest solutions from my search, all 4 moves: P1 `R' B D R'`, P2 `B2 L B2 F`,
P3 `U' F L2 B'`, P4 `R' D' R' U2`, P5 `D B' U' L2`.

What I saw:
- **Jev** used all 30 moves on every puzzle and mostly repeated or undid the same face: `U U' U U' …`, `R R' R R' …`, and on P5 `U2` thirty times in a row.
- **Clef** also used all 30 moves every time, in the same kind of loop (`U2 U' U U' …`, `D D D D D' D'`).
- **Luna** refused all 150 requests with *"OpenAI refused to answer question next_move"* (HTTP 502). The same request worked in my warm-up, so the model was refusing; it wasn't a bug in my code.
- Even with 30 moves for a 4-move puzzle, 26 spare moves, neither working model got close.
- In the warm-up the cube was only one move from solved (the answer was `R'`). Jev chose `U`, Luna `F` and Clef `U'`, so none of them found it.

## Answers to the experiment questions

1. **Which model is fastest?** Jev 1.13, at 0.78 s per move on average (median 0.74 s). Clef took 1.13 s and Luna 1.41 s, and Luna's times are for refusals.
2. **Which model had the highest solve rate?** None. Every model I tested solved 0 of 5 puzzles within 30 moves.
3. **Which model found the shortest solutions?** None solved a puzzle, so I couldn't measure an optimality gap. The optimum was 4 moves for every puzzle.
4. **Did the fastest model also give the best quality?** No. Jev was the fastest, but it spent its 30 moves repeating the same face turns, so its speed didn't help.
5. **What would I use in a real application?** A hybrid. The decision models are built for single-step choices, and solving a cube needs planning several moves ahead. They didn't show that, even with 26 spare moves. My breadth-first search found every optimal solution in milliseconds on a normal CPU. In a real system I would let a search or planner handle the multi-step work and use a fast decision model only for quick single-step decisions. I couldn't test the frontier LLM side because of credit and rate limits, so whether Opus would do better is still an open question in my results.

## Folder layout

```
assignment_2/
  backend/   app.py  adapters.py  benchmark.py  budget.py  config.py  cube.py  make_slide.py  solver.py
  frontend/  index.html
  data/      results.json  results_limit5.json  warmup.json  decision_models_catalog.json  api_call_ledger.json
  tests/     test_cube.py
  results_slide.html  README.md  requirements.txt  .env.example
```
