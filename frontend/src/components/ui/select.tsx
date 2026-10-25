import * as React from "react"
import { cn } from "@/lib/utils"

function Select({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="select"
      className={cn(
        "border-input bg-background text-foreground flex h-9 w-full rounded-lg border px-3 py-1 text-[13px] font-medium shadow-2xs transition-colors outline-none cursor-pointer focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/25 hover:border-brand-300 dark:hover:border-brand-700 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
}

export { Select }
