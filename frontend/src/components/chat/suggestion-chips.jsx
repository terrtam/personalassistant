import { Button } from '../ui/button'

export function SuggestionChips({ suggestions, onSelect }) {
  return (
    <div className="flex flex-wrap gap-2">
      {suggestions.map((suggestion) => (
        <Button
          className="rounded-full border-slate-200 bg-white text-xs font-medium text-slate-600 hover:bg-slate-50"
          key={suggestion}
          onClick={() => onSelect(suggestion)}
          size="sm"
          type="button"
          variant="outline"
        >
          {suggestion}
        </Button>
      ))}
    </div>
  )
}
