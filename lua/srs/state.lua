local state = {
	proc = nil,
	repo_root = nil,
	win = nil,
	buf = nil,
	prev_buf = nil,
	quitting = false,
	mode = "idle", -- "intro" | "question" | "rating" | "idle"
	card = nil,
	due = nil,
	paused = false,
	ns = nil,
	cloze_open = "~{",
	cloze_close = "}",
	saved_win = nil,
	touched = {},
	keymaps = {},
}

function state.reset()
	state.mode = "idle"
	state.card = nil
	state.due = nil
	state.paused = false
	state.buf = nil
	state.repo_root = nil
	state.saved_win = nil
	state.touched = {}
	state.keymaps = {}
	state.ns = vim.api.nvim_create_namespace("srs")
end

function state.restore()
	for buf in pairs(state.touched) do
		if vim.api.nvim_buf_is_valid(buf) and state.ns then
			vim.api.nvim_buf_clear_namespace(buf, state.ns, 0, -1)
		end
	end
	if state.saved_win and state.win and vim.api.nvim_win_is_valid(state.win) then
		pcall(vim.api.nvim_win_call, state.win, function()
			vim.cmd("silent! normal! zE")
		end)
	end
	for buf, keys in pairs(state.keymaps) do
		if vim.api.nvim_buf_is_valid(buf) then
			for lhs in pairs(keys) do
				pcall(vim.keymap.del, "n", lhs, { buffer = buf })
			end
		end
	end
	state.keymaps = {}

	if
		state.win
		and vim.api.nvim_win_is_valid(state.win)
		and state.prev_buf
		and vim.api.nvim_buf_is_valid(state.prev_buf)
	then
		vim.api.nvim_win_set_buf(state.win, state.prev_buf)
	end

	if state.saved_win and state.win and vim.api.nvim_win_is_valid(state.win) then
		local saved = state.saved_win
		vim.wo[state.win].foldmethod = saved.foldmethod
		vim.wo[state.win].foldenable = saved.foldenable
		vim.wo[state.win].foldlevel = saved.foldlevel
		vim.wo[state.win].statusline = saved.statusline
	end

	state.touched = {}
	state.saved_win = nil
	state.mode = "idle"
	state.card = nil
end

return state
