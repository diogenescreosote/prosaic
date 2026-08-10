/* prosaic-runner — launchd shim for scheduled matter syncs (macOS).
 *
 * Why this exists: macOS TCC blocks background launchd jobs from
 * reading protected locations (Desktop, Documents, and — critically —
 * ~/Library/CloudStorage, where cloud-synced matter directories live).
 * TCC grants attach to a binary; scripts are attributed to their
 * interpreter, and copies of platform binaries (e.g. a copied
 * /bin/bash) are killed outright by the OS. So we ship this trivial,
 * locally compiled shim: launchd runs it, you grant IT Full Disk
 * Access once (System Settings → Privacy & Security → Full Disk
 * Access), and every child process (bash, node, claude) inherits the
 * grant via responsible-process attribution — the same mechanism that
 * makes granting FDA to cron cover all cron jobs.
 *
 * Build:  cc -O2 -o ~/.local/bin/prosaic-runner runner_shim.c
 * Usage:  prosaic-runner <script.sh> [args...]
 *         (spawns /bin/bash <script.sh> [args...])
 */
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s <script.sh> [args...]\n", argv[0]);
        return 64;
    }
    char **args = calloc(argc + 2, sizeof(char *));
    args[0] = "/bin/bash";
    for (int i = 1; i < argc; i++) args[i] = argv[i];
    args[argc] = NULL;

    pid_t pid;
    int rc = posix_spawn(&pid, "/bin/bash", NULL, NULL, args, environ);
    if (rc != 0) {
        fprintf(stderr, "posix_spawn failed: %s\n", strerror(rc));
        return 127;
    }
    int status = 0;
    waitpid(pid, &status, 0);
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    return 128 + (WIFSIGNALED(status) ? WTERMSIG(status) : 1);
}
