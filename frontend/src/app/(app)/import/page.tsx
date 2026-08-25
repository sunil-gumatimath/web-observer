"use client";

import { useState, type FormEvent } from "react";
import {
	Button,
	Card,
	ErrorBox,
	Label,
	PageHeader,
	SegmentedControl,
	SuccessBox,
	Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";
import type { MonitorCreateInput } from "@/lib/types";

const CSV_DEFAULT =
	"name,url,mode,schedule_interval_minutes\nExample,https://example.com/,page_content,60\n";

const JSON_DEFAULT: MonitorCreateInput[] = [
	{
		name: "Example",
		url: "https://example.com/",
		mode: "page_content",
		schedule_interval_minutes: 60,
	},
];

const JSON_EXAMPLE = JSON.stringify(JSON_DEFAULT, null, 2);

export default function ImportPage() {
	usePageTitle("Bulk import");
	const [mode, setMode] = useState<"csv" | "json">("csv");
	const [csvText, setCsvText] = useState(CSV_DEFAULT);
	const [jsonText, setJsonText] = useState(JSON_EXAMPLE);
	const [result, setResult] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);

	function switchMode(next: "csv" | "json") {
		setMode(next);
		setError(null);
		setResult(null);
	}

	async function onSubmit(e: FormEvent) {
		e.preventDefault();
		setBusy(true);
		setError(null);
		setResult(null);
		try {
			const ws = await ensureWorkspace();
			let res;
			if (mode === "csv") {
				res = await api.bulkImportMonitors(ws, { csvText });
			} else {
				let items: MonitorCreateInput[];
				try {
					const parsed = JSON.parse(jsonText);
					items = Array.isArray(parsed) ? parsed : [parsed];
				} catch {
					throw new Error(
						"Invalid JSON: expected an array of monitor objects.",
					);
				}
				if (items.length === 0) throw new Error("No items provided.");
				res = await api.bulkImportMonitors(ws, { jsonItems: items });
			}
			const errors = res.errors ?? [];
			setResult(
				`Created ${res.created_count}. Skipped ${res.skipped?.length ?? 0}. Errors ${errors.length}.`,
			);
			if (errors.length > 0) {
				setError(errors.map((e) => `Row ${e.row}: ${e.error}`).join("\n"));
			}
		} catch (err) {
			setError(err instanceof Error ? err.message : "Import failed");
		} finally {
			setBusy(false);
		}
	}

	return (
		<div>
			<PageHeader
				title="Bulk import"
				description="Import monitors from CSV or JSON (name, url, mode, schedule_interval_minutes). Modes: page_content, site_links, product_price, list_items, json_field."
			/>
			{error ? <ErrorBox message={error} /> : null}
			{result ? <SuccessBox message={result} /> : null}
			<Card className="max-w-3xl">
				<form onSubmit={onSubmit} className="space-y-4">
					<SegmentedControl
						ariaLabel="Import format"
						value={mode}
						onChange={switchMode}
						options={[
							{ value: "csv", label: "CSV" },
							{ value: "json", label: "JSON" },
						]}
					/>
					{mode === "csv" ? (
						<div>
							<Label htmlFor="csv">CSV</Label>
							<Textarea
								id="csv"
								className="h-64 font-mono text-xs"
								value={csvText}
								onChange={(e) => setCsvText(e.target.value)}
							/>
						</div>
					) : (
						<div>
							<Label htmlFor="json">JSON (array of monitor objects)</Label>
							<Textarea
								id="json"
								className="h-64 font-mono text-xs"
								value={jsonText}
								onChange={(e) => setJsonText(e.target.value)}
							/>
						</div>
					)}
					<Button type="submit" disabled={busy}>
						{busy ? "Importing…" : "Import monitors"}
					</Button>
				</form>
			</Card>
		</div>
	);
}
