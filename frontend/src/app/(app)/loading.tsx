import { SkeletonCard, SkeletonStats } from "@/components/skeleton";

export default function AppLoading() {
  return (
    <div suppressHydrationWarning className="space-y-4">
      <SkeletonStats />
      <div suppressHydrationWarning className="space-y-2">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </div>
  );
}
