import { ChevronLeft, ChevronRight } from 'lucide-react'
import { DayPicker } from 'react-day-picker'

import { cn } from '../../lib/utils'
import { buttonVariants } from './button'

function Calendar({ className, classNames, showOutsideDays = true, ...props }) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      navLayout="around"
      className={cn('p-3', className)}
      classNames={{
        root: 'p-0',
        months: 'flex flex-col gap-4 sm:flex-row sm:gap-6',
        month: 'grid grid-cols-[1fr,auto,1fr] grid-rows-[auto,1fr] items-center gap-y-4',
        month_caption: 'col-start-2 row-start-1 flex items-center justify-center pt-1',
        caption_label: 'text-sm font-medium text-slate-900',
        nav: 'relative flex items-center justify-between',
        button_previous: cn(
          buttonVariants({ variant: 'ghost', size: 'icon' }),
          'col-start-1 row-start-1 h-7 w-7 justify-self-start bg-transparent p-0 opacity-60 hover:opacity-100',
        ),
        button_next: cn(
          buttonVariants({ variant: 'ghost', size: 'icon' }),
          'col-start-3 row-start-1 h-7 w-7 justify-self-end bg-transparent p-0 opacity-60 hover:opacity-100',
        ),
        month_grid: 'col-span-3 row-start-2 w-full border-collapse',
        weekdays: 'grid w-full grid-cols-7',
        weekday: 'h-9 w-9 text-center text-[0.8rem] font-normal text-slate-500',
        weeks: 'grid w-full gap-y-2',
        week: 'grid w-full grid-cols-7',
        day: 'flex h-9 w-9 items-center justify-center rounded-full p-0 text-slate-700',
        day_button: cn(
          buttonVariants({ variant: 'ghost' }),
          'h-9 w-9 rounded-full p-0 font-normal text-inherit',
        ),
        day_selected: 'bg-slate-900 text-white',
        day_today: 'bg-slate-100 text-slate-900',
        day_outside: 'text-slate-400 opacity-50',
        day_disabled: 'text-slate-400 opacity-50',
        day_range_middle: 'bg-slate-100 text-slate-900',
        day_hidden: 'invisible',
        ...classNames,
      }}
      components={{
        IconLeft: () => <ChevronLeft className="h-4 w-4" />,
        IconRight: () => <ChevronRight className="h-4 w-4" />,
      }}
      {...props}
    />
  )
}

export { Calendar }
