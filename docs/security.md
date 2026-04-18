# Security in Sekai

Let's be real: Sekai isn't a bulletproof sandbox, but it’s got a solid three-layer defense to keep things from breaking. It’s less of a "vault" and more of a "smart fence"—it keeps honest people honest and makes it much harder for shady modules to mess with your bot.

## The Three Layers
1. **ACL (Access Control):** Basic "Who are you?" check using Owners, Sudos, and temporary permissions.
2. **Static Check:** We scan community modules **before** they even load. If we see something suspicious, they don't get to run.
3. **Runtime Firewall:** A live "audit hook" that watches what the code is doing while it's running (like trying to delete files or touch raw memory).

---

## 1. The "Pre-Load" Scan (Static Analysis)
When you try to load a **community module**, we peek at its source code using AST (Abstract Syntax Tree) before it even compiles. 

### What’s on the Blacklist?
If a module tries to touch these directly, it’s **blocked immediately**:
*   **Session control:** `login`, `logout`, `stop`, `start`.
*   **Sensitive data:** `crypto`, `api` (the raw client), `device_id`.
*   **Sneaky tricks:** If you try to bypass the scan using `getattr(client, "crypto")`, we’ll catch that too by scanning for forbidden strings.

**Result:** If the module is sketchy, it simply won't load. Period.

---

## 2. The Runtime Firewall
If a module makes it past the scan, we still watch it live. We use a lightweight frame-checker (`sys._getframe`) to see if the caller is a community module.

### What we block in real-time:
*   **Writing files:** You can read files, but you can't write, append, or delete them.
*   **Core hijacking:** Community modules can't import internal "Core" modules.
*   **Memory hacks:** No `ctypes` allowed. You can't touch C-level memory.

---

## The Reality Check (Limitations)
Don't get overconfident. This is a userbot, not a high-security OS. 
*   **No process isolation:** Everything still runs in one process.
*   **Reading is allowed:** A module can still read your local files (for now).
*   **Network is open:** Modules can still talk to the internet and external APIs.
*   **It’s a Blacklist:** We block known bad paths, but a determined "hacker" might find a new one.

**The Golden Rule:** Only install modules from people you trust. Read the code if you're unsure. This security system is here to help, but your common sense is still the best defense.