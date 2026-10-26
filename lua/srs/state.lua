local state = {
	proc = nil,
	repo_root = nil,
	win = nil,
	buf = nil,
	prev_buf = nil,
	quitting = false,
	mode = "idle", -- "question" | "rating" | "idle"
	card = nil,
	paused = false,
	ns = nil,
	cloze_open = "~{",
	cloze_close = "}",
	saved_win = nil,
	touched = {},
	keymaps = {},
}

function state.valid_buf(buf)
	return buf ~= nil and vim.api.nvim_buf_is_valid(buf)
end

function state.valid_win(win)
	return win ~= nil and vim.api.nvim_win_is_valid(win)
end

function state.reset()
	state.mode = "idle"
	state.card = nil
	state.paused = false
	state.buf = nil
	state.repo_root = nil
	state.saved_win = nil
	state.touched = {}
	state.keymaps = {}
	state.ns = vim.api.nvim_create_namespace("srs")
end

function state.restore()
	local win = state.win
	local win_ok = state.valid_win(win)
	local saved = state.saved_win

	for buf in pairs(state.touched) do
		if state.valid_buf(buf) and state.ns then
			vim.api.nvim_buf_clear_namespace(buf, state.ns, 0, -1)
		end
	end
	if saved and win_ok then
		pcall(vim.api.nvim_win_call, win, function()
			vim.cmd("silent! normal! zE")
		end)
	end
	for buf, keys in pairs(state.keymaps) do
		if state.valid_buf(buf) then
			for lhs in pairs(keys) do
				pcall(vim.keymap.del, "n", lhs, { buffer = buf })
			end
		end
	end
	state.keymaps = {}

	if win_ok and state.prev_buf and state.valid_buf(state.prev_buf) then
		vim.api.nvim_win_set_buf(win, state.prev_buf)
	end

	if saved and win_ok then
		vim.wo[win].foldmethod = saved.foldmethod
		vim.wo[win].foldenable = saved.foldenable
		vim.wo[win].foldlevel = saved.foldlevel
		vim.wo[win].statusline = saved.statusline
	end

	state.touched = {}
	state.saved_win = nil
	state.mode = "idle"
	state.card = nil
end

return state
