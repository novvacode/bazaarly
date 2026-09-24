"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CopyButton } from "@/components/copy-button";
import { PageHeader } from "@/components/dashboard/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { InviteCreatedOut, MemberOut, TeamOut } from "@/lib/types";

const dateFmt = new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" });

export default function TeamPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const team = useQuery({ queryKey: ["team"], queryFn: () => api<TeamOut>("/team") });
  const [invite, setInvite] = useState<InviteCreatedOut | null>(null);
  const [removing, setRemoving] = useState<MemberOut | null>(null);

  const createInvite = useMutation({
    mutationFn: () => api<InviteCreatedOut>("/team/invites", { body: { role: "staff" } }),
    onSuccess: (inv) => {
      setInvite(inv);
      void queryClient.invalidateQueries({ queryKey: ["team"] });
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  const remove = useMutation({
    mutationFn: (m: MemberOut) =>
      api<void>(`/team/memberships/${m.membership_id}`, { method: "DELETE" }),
    onSuccess: () => {
      setRemoving(null);
      toast.success("Member removed");
      void queryClient.invalidateQueries({ queryKey: ["team"] });
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  return (
    <>
      <PageHeader
        title="Team"
        description="Staff can see the menu and manage orders. Only owners change settings."
        actions={
          <Button onClick={() => createInvite.mutate()} disabled={createInvite.isPending}>
            <Link2 /> Create invite link
          </Button>
        }
      />

      {invite && (
        <Card className="border-primary/40 mb-6">
          <CardHeader>
            <CardTitle>Invite link ready</CardTitle>
            <CardDescription>
              Share it with your staff member (e.g. on WhatsApp). It works once and expires on{" "}
              {dateFmt.format(new Date(invite.expires_at))}.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3">
            <code className="bg-muted rounded px-2 py-1 text-sm break-all">{invite.url}</code>
            <CopyButton value={invite.url} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent>
          {team.isPending ? (
            <Skeleton className="h-32 w-full" />
          ) : team.isError ? (
            <p className="text-destructive">{errorMessage(team.error)}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Joined</TableHead>
                  <TableHead className="w-12">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {team.data.members.map((m) => (
                  <TableRow key={m.membership_id}>
                    <TableCell className="font-medium">{m.name}</TableCell>
                    <TableCell>{m.email}</TableCell>
                    <TableCell>
                      <Badge variant={m.role === "owner" ? "default" : "secondary"}>{m.role}</Badge>
                    </TableCell>
                    <TableCell>{dateFmt.format(new Date(m.joined_at))}</TableCell>
                    <TableCell>
                      {m.user_id !== user?.id && (
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Remove ${m.name}`}
                          onClick={() => setRemoving(m)}
                        >
                          <Trash2 />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {team.data && team.data.pending_invites.length > 0 && (
            <p className="text-muted-foreground mt-4 text-sm">
              {team.data.pending_invites.length} pending invite
              {team.data.pending_invites.length > 1 ? "s" : ""}.
            </p>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!removing} onOpenChange={(o) => !o && setRemoving(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove {removing?.name}?</DialogTitle>
            <DialogDescription>
              They&apos;ll lose access to this business immediately.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => removing && remove.mutate(removing)}
            >
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
