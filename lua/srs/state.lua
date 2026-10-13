local state = {
	proc = nil,
	win = nil,
	buf = nil,
	prev_buf = nil,
	quitting = false,
	mode = "idle", -- "intro" | "question" | "rating" | "idle"
	buttons = {},
	suggested = nil,
	card = nil,
	duration_s = nil,
	due = nil,
}

function state.reset()
	state.mode = "idle"
	state.buttons = {}
	state.suggested = nil
	state.card = nil
	state.duration_s = nil
	state.due = nil
end

function state.restore()
	if
		state.win
		and vim.api.nvim_win_is_valid(state.win)
		and state.prev_buf
		and vim.api.nvim_buf_is_valid(state.prev_buf)
	then
		vim.api.nvim_win_set_buf(state.win, state.prev_buf)
	end
	state.mode = "idle"
end

return state
