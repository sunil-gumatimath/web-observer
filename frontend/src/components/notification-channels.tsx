"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ConfirmButton } from "@/components/confirm-dialog";
import {
	Badge,
	Button,
	Card,
	ErrorBox,
	Input,
	Label,
	Select,
	SuccessBox,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { NotificationChannel } from "@/lib/types";

export function NotificationChannelsPanel({
	workspaceId,
}: {
	workspaceId: string;
}) {
	const [channels, setChannels] = useState<NotificationChannel[]>([]);
	const [type, setType] = useState<"email" | "slack" | "discord">("email");
	const [address, setAddress] = useState("");
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);
	const [busyId, setBusyId] = useState<string | null>(null);
	const [adding, setAdding] = useState(false);
	const [testMsg, setTestMsg] = useState<string | null>(null);

	const load = useCallback(async () => {
		const list = await api.listNotificationChannels(workspaceId);
		setChannels(list);
	}, [workspaceId]);

	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				await load();
			} catch (e) {
				if (!cancelled)
					setError(e instanceof Error ? e.message : "Failed to load channels");
			} finally {
				if (!cancelled) setLoading(false);
			}
		})();
		return () => {
			cancelled = true;
		};
	}, [load]);
	async function onAdd(e: FormEvent) {
		e.preventDefault();
		setAdding(true);
		setError(null);
		try {
			await api.createNotificationChannel(workspaceId, { type, address });
			setAddress("");
			await load();
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to add channel");
		} finally {
			setAdding(false);
		}
	}
	async function toggle(channel: NotificationChannel) {
		setBusyId(channel.id);
		setError(null);
		try {
			await api.updateNotificationChannel(workspaceId, channel.id, {
				enabled: !channel.enabled,
			});
			await load();
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to update channel");
		} finally {
			setBusyId(null);
		}
	}

	async function test(channel: NotificationChannel) {
		setBusyId(channel.id);
		setError(null);
		setTestMsg(null);
		try {
			const res = await api.testNotificationChannel(workspaceId, channel.id);
			setTestMsg(res.detail);
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to send test");
		} finally {
			setBusyId(null);
		}
	}

	async function remove(channel: NotificationChannel) {
		setBusyId(channel.id);
		setError(null);
		try {
			await api.deleteNotificationChannel(workspaceId, channel.id);
			await load();
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to delete channel");
		} finally {
			setBusyId(null);
		}
	}

	return (
		<div className="space-y-4">
			{error ? <ErrorBox message={error} /> : null}
			{testMsg ? <SuccessBox message={testMsg} /> : null}

			<Card>
				<p className="mb-4 text-sm text-slate-600 dark:text-slate-400">
					Enabled channels receive change alerts (and digests when configured).
					Use a Slack or Discord <strong>incoming webhook</strong> URL for team
					chat.
				</p>
				<div className="space-y-2">
					{channels.map((c) => (
						<div
							key={c.id}
							className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-slate-50/60 px-3.5 py-3 dark:bg-slate-950/40"
						>
							<div className="min-w-0">
								<p className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
									{c.address}
								</p>
								<p className="mt-0.5 text-xs capitalize text-slate-500 dark:text-slate-500">
									{c.type}
								</p>
							</div>
							<div className="flex items-center gap-2">
								<Badge tone={c.enabled ? "success" : "warn"}>
									{c.enabled ? "enabled" : "disabled"}
								</Badge>
								<Button
									type="button"
									variant="secondary"
									size="sm"
									disabled={busyId === c.id}
									onClick={() => toggle(c)}
								>
									{c.enabled ? "Disable" : "Enable"}
								</Button>
								<Button
									type="button"
									variant="ghost"
									size="sm"
									disabled={busyId === c.id}
									onClick={() => test(c)}
								>
									Send test
								</Button>
								<ConfirmButton
									variant="danger"
									size="sm"
									busy={busyId === c.id}
									error={error}
									onConfirm={() => remove(c)}
									title={`Remove ${c.type} channel?`}
									body="This channel will immediately stop receiving change alerts."
								>
									Remove
								</ConfirmButton>
							</div>
						</div>
					))}
					{channels.length === 0 ? (
						<p className="rounded-lg border border-dashed border-[var(--border-strong)] px-3 py-6 text-center text-sm text-slate-500 dark:text-slate-500">
							{loading ? "Loading channels…" : "No channels yet."}
						</p>
					) : null}
				</div>
			</Card>

			<Card>
				<form onSubmit={onAdd} className="space-y-4">
					<div>
						<Label htmlFor="ctype">Channel type</Label>
						<Select
							id="ctype"
							value={type}
							onChange={(e) =>
								setType(e.target.value as "email" | "slack" | "discord")
							}
						>
							<option value="email">Email</option>
							<option value="slack">Slack webhook</option>
							<option value="discord">Discord webhook</option>
						</Select>
					</div>
					<div>
						<Label htmlFor="addr">
							{type === "email" ? "Email address" : "Webhook URL (https)"}
						</Label>
						<Input
							id="addr"
							required
							type={type === "email" ? "email" : "url"}
							value={address}
							onChange={(e) => setAddress(e.target.value)}
							placeholder={
								type === "email"
									? "alerts@company.com"
									: "https://hooks.slack.com/services/..."
							}
						/>
					</div>
					<Button type="submit" disabled={adding}>
						{adding ? "Adding…" : "Add channel"}
					</Button>
				</form>
			</Card>
		</div>
	);
}
