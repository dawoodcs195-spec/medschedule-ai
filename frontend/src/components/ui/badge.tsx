import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors select-none",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground",
        outline:
          "border-border text-foreground bg-background",
        destructive:
          "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950/50 dark:text-rose-300",
        sky:
          "border-sky-200/90 bg-sky-50/90 text-sky-900 dark:border-sky-800/70 dark:bg-sky-950/50 dark:text-sky-200",
        emerald:
          "border-emerald-200/90 bg-emerald-50/90 text-emerald-900 dark:border-emerald-800/70 dark:bg-emerald-950/50 dark:text-emerald-200",
        amber:
          "border-amber-200/90 bg-amber-50/90 text-amber-900 dark:border-amber-800/70 dark:bg-amber-950/50 dark:text-amber-200",
        purple:
          "border-purple-200/90 bg-purple-50/90 text-purple-900 dark:border-purple-800/70 dark:bg-purple-950/50 dark:text-purple-200",
        slate:
          "border-slate-200/90 bg-slate-100/80 text-slate-700 dark:border-zinc-700 dark:bg-zinc-800/80 dark:text-zinc-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span
      data-slot="badge"
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
