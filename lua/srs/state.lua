local NS = vim.api.nvim_create_namespace("srs")

local WIN_OPTS = { "foldmethod", "foldenable", "foldlevel", "statusline" }

local state = { ns = NS }

function state.reset()
	state.proc = nil
	state.repo_root = nil
	state.win = nil
	state.buf = nil
	state.prev_buf = nil
	state.quitting = false
	state.mode = "idle"
	state.card = nil
	state.paused = false
	state.cloze_open = "~{"
	state.cloze_close = "}"
	state.saved_win = nil
	state.keymaps = {}
end

function state.valid_buf(buf)
	return buf ~= nil and vim.api.nvim_buf_is_valid(buf)
end

function state.valid_win(win)
	return win ~= nil and vim.api.nvim_win_is_valid(win)
end

function state.win_cmd(win, cmd)
	if state.valid_win(win) then
		vim.api.nvim_win_call(win, function() vim.cmd(cmd) end)
	end
end

function state.clear_folds(win)
	state.win_cmd(win, "silent! normal! zE")
end

function state.clear_marks(buf)
	if state.valid_buf(buf) then
		vim.api.nvim_buf_clear_namespace(buf, state.ns, 0, -1)
	end
end

function state.save_window(win)
	if not state.saved_win then
		local saved = {}
		for _, name in ipairs(WIN_OPTS) do
			saved[name] = vim.wo[win][name]
		end
		state.saved_win = saved
	end
end

function state.restore()
	local win = state.win
	local win_ok = state.valid_win(win)
	local saved = state.saved_win

	state.clear_marks(state.buf)
	if saved and win_ok then
		state.clear_folds(win)
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
		for _, name in ipairs(WIN_OPTS) do
			vim.wo[win][name] = saved[name]
		end
	end

	state.saved_win = nil
	state.mode = "idle"
	state.card = nil
end

state.reset()

return state
