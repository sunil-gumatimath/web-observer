import { redirect } from "next/navigation";
import { requireSession } from "@/lib/server-auth";

// eslint-disable-next-line @clerk/next/require-auth-protection -- Protected by requireSession(), the dev-mode-aware wrapper around auth.protect().
export default async function ChangesPage() {
	await requireSession();
	redirect("/alerts");
}
