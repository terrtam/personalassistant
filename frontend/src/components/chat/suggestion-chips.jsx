export function SuggestionChips({ suggestions, onSelect }) {
  return (
    <div className="suggestions">
      {suggestions.map((suggestion) => (
        <button
          className="chip"
          key={suggestion}
          onClick={() => onSelect(suggestion)}
          type="button"
        >
          {suggestion}
        </button>
      ))}
    </div>
  )
}
