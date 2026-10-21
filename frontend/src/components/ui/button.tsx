import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all duration-200 cursor-pointer outline-none select-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-xs hover:bg-primary/90",
        destructive:
          "bg-rose-50 text-rose-700 border border-rose-200/90 hover:bg-rose-100/90 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800/80 dark:hover:bg-rose-900/50",
        outline:
          "border border-border bg-card text-foreground shadow-2xs hover:bg-muted/70 hover:text-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "text-muted-foreground hover:bg-muted hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
        brand:
          "bg-indigo-600 text-white shadow-xs hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600",
        soft:
          "bg-indigo-50/90 text-indigo-700 border border-indigo-200/80 hover:bg-indigo-100/80 dark:bg-indigo-950/50 dark:text-indigo-300 dark:border-indigo-800/70 dark:hover:bg-indigo-900/50",
        amber:
          "bg-amber-50/90 text-amber-800 border border-amber-200/90 hover:bg-amber-100/80 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800/70",
        emerald:
          "bg-emerald-50/90 text-emerald-800 border border-emerald-200/90 hover:bg-emerald-100/80 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800/70",
      },
      size: {
        default: "h-8 px-3 py-1.5",
        xs: "h-7 px-2.5 text-[11px] rounded-md",
        sm: "h-8 px-3 text-xs rounded-lg",
        lg: "h-9 px-4 text-xs font-semibold rounded-lg",
        icon: "size-8 rounded-lg",
        "icon-sm": "size-7 rounded-md",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, type = "button", ...props }, ref) => {
    return (
      <button
        type={type}
        ref={ref}
        data-slot="button"
        className={cn(buttonVariants({ variant, size, className }))}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
