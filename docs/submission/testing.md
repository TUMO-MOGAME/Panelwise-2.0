# Devpost — "Testing instructions" (draft)

> Working copy of Devpost's testing-instructions field. Paste **everything below the line**, and put
> the judge account's email and password in the field itself, where the marked line is. The
> credentials never go in the repo (limits.md §1; web.md §10). Figures checked against
> render.yaml, limits.md and deploy.md §6 on 2026-10-27.

---

**Open https://panelwise.vercel.app and sign in with the shared judge account:**

⟨judge email and password: pasted on Devpost only⟩

Sign-up is off, so this account is the way in. It already holds **the-red-kite**, a five-page
sample screenplay we wrote, drawn end to end on the hosted stack. Nothing needs to run for you to
see the whole product:

1. **Script:** every character, prop and location the model found, each with the exact script
   lines it came from.
2. **Storyboard:** one frame per shot beside the script. Click a frame for its audit log: what the
   vision model saw, what Nemotron judged, every check, and every redraw. *Export PDF* gives the storyboard as a PDF.
3. **Comic:** the same script as comic pages, every speech bubble lettered word for word from the
   script. Click any bubble to see the line it came from. *Download PDF* gives the comic as a PDF.

**To try your own upload**, drop a screenplay PDF of up to 15 pages on *Board your script* on the
projects page. Any PDF in the repo's [`samples/`](https://github.com/Katlego-tech/Panelwise/tree/main/samples)
folder works (all self-written, 4 to 10 pages). A storyboard takes a few minutes, and you can watch
its frames arrive one by one. Then press *Make the comic* on its comic tab.

**Why the demo has limits.** We're two students building this on our own money: we pay for the
hosting and for every drawing ourselves, and every model call runs on the Nebius Builder Program
credit. So that the demo stays up and free for you until judging ends on 15 Dec, it has caps:

- **3 uploads per account in any 24 hours.** All judges share one account, so the 3 are shared
  too. If you see "This demo makes 3 storyboards a day per account", someone has used today's
  three; the seeded project still opens, and uploading works again within a day.
- **15 pages a script.** Longer scripts are refused at upload, before anything is spent.
- **A monthly budget** of 2,800,000 Token Factory tokens and 800 drawings, shared by everyone:
  about seven new storyboards with their comics a month. Both reset on the 1st (UTC), so judging
  in December starts with a full budget. At the budget, new work is refused with a message, a job
  already running finishes, and every existing storyboard and comic still opens.

If anything doesn't work, the video shows the full path, and the README's *How to run it* runs
the same app locally with your own keys and no caps.
