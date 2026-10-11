local M = {}

local REVEAL_KEYS = "abcdefghijklmnopqrstuvwxyz0123456789"

local state = {
	proc = nil,
	win = nil,
	buf = nil,
	prev_buf = nil,
	quitting = false,
	mode = "idle", -- "intro" | "question" | "rating" | "idle"
	buttons = {},
}

function M.setup(opts)
	M.config = opts or {}
	if vim.g.loaded_srs_nvim ~= 1 then
		vim.g.loaded_srs_nvim = 1
		vim.api.nvim_create_user_command("SrsReview", function()
			M.review()
		end, { desc = "Start an SRS review session" })
	end
	return M
end

-- Environment ---------------------------------------------------------------

local function plugin_root()
	return vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h:h")
end

local function python()
	local venv = vim.env.VIRTUAL_ENV
	if venv and venv ~= "" and vim.fn.executable(venv .. "/bin/python") == 1 then
		return venv .. "/bin/python"
	end
	return "python3"
end

-- Rendering -----------------------------------------------------------------

local function set_lines(lines)
	vim.bo[state.buf].modifiable = true
	vim.api.nvim_buf_set_lines(state.buf, 0, -1, false, lines)
	vim.bo[state.buf].modifiable = false
	vim.api.nvim_win_set_cursor(state.win, { 1, 0 })
end

local function screen(title, body)
	local lines = {}
	if title ~= "" then
		vim.list_extend(lines, vim.split(title, "\n", { plain = true }))
	end
	if body ~= "" then
		vim.list_extend(lines, vim.split(body, "\n", { plain = true }))
	end
	set_lines(lines)
end

local function set_note_name(path)
	if not path or path == "" then
		return
	end
	if not pcall(vim.api.nvim_buf_set_name, state.buf, path) then
		pcall(vim.api.nvim_buf_set_name, state.buf, vim.fn.fnamemodify(path, ":t") .. " [srs]")
	end
end

local function render_note(message)
	set_note_name(message.note)
	local parts = {}
	for _, segment in ipairs(message.segments or {}) do
		table.insert(parts, segment.text)
	end
	local lines = vim.split(table.concat(parts), "\n", { plain = true })
	if lines[#lines] == "" then
		table.remove(lines)
	end
	set_lines(lines)
end

-- Events --------------------------------------------------------------------

local function send(event)
	if state.proc then
		state.proc:write(vim.json.encode(event) .. "\n")
	end
end

local function handle_message(message)
	if not vim.api.nvim_buf_is_valid(state.buf) then
		return
	end
	local kind = message.type
	if kind == "intro" then
		state.mode = "intro"
		screen("Due cards: " .. tostring(message.total or 0), table.concat(message.notes or {}, "\n"))
	elseif kind == "render" then
		state.mode = message.state
		render_note(message)
	elseif kind == "rating" then
		state.mode = "rating"
		state.buttons = message.buttons or {}
	elseif kind == "message" then
		if message.text ~= "" then
			screen("", message.text)
		end
	elseif kind == "error" then
		screen("error", message.text or "")
	end
end

local function handle_key(key)
	if state.mode == "rating" then
		for name, char in pairs(state.buttons) do
			if char == key then
				send({ name = "rate", rating = name })
				return
			end
		end
	elseif state.mode == "question" then
		send({ name = "reveal", label = key })
	end
end

-- Session -------------------------------------------------------------------

local function setup_keymaps()
	vim.keymap.set("n", "<CR>", function()
		if state.mode == "intro" then
			send({ name = "start" })
		elseif state.mode == "question" then
			send({ name = "next" })
		elseif state.mode == "rating" then
			send({ name = "rate" })
		end
	end, { buffer = state.buf, desc = "SRS next" })

	vim.keymap.set("n", "<Esc>", M.close, { buffer = state.buf, desc = "SRS quit" })

	for key in REVEAL_KEYS:gmatch(".") do
		vim.keymap.set("n", key, function()
			handle_key(key)
		end, { buffer = state.buf })
	end
end

function M.review()
	if state.proc then
		vim.notify("srs: review already running", vim.log.levels.WARN)
		return
	end

	local repo_root = vim.fs.root(0, { ".git", ".srs" })
	if not repo_root then
		vim.notify("srs: not inside a git repository", vim.log.levels.ERROR)
		return
	end

	state.prev_buf = vim.api.nvim_get_current_buf()
	state.win = vim.api.nvim_get_current_win()
	state.buf = vim.api.nvim_create_buf(false, true)
	vim.bo[state.buf].filetype = "markdown"
	vim.bo[state.buf].bufhidden = "wipe"
	vim.api.nvim_win_set_buf(state.win, state.buf)
	state.quitting = false
	setup_keymaps()

	local buffered = ""
	local function on_stdout(_, data)
		buffered = buffered .. (data or "")
		while true do
			local newline = buffered:find("\n", 1, true)
			if not newline then
				break
			end
			local line = buffered:sub(1, newline - 1)
			buffered = buffered:sub(newline + 1)
			if line ~= "" then
				local ok, message = pcall(vim.json.decode, line)
				if ok then
					vim.schedule(function()
						handle_message(message)
					end)
				end
			end
		end
	end

	state.proc = vim.system({ python(), plugin_root() .. "/core/rpc.py" }, {
		cwd = repo_root,
		stdin = true,
		stdout = on_stdout,
		stderr = function(_, data)
			if data and data ~= "" then
				vim.schedule(function()
					vim.notify("srs: " .. vim.trim(data), vim.log.levels.WARN)
				end)
			end
		end,
		text = true,
	}, function(completed)
		vim.schedule(function()
			state.proc = nil
			if completed.code ~= 0 and not state.quitting then
				vim.notify("srs: process exited with code " .. tostring(completed.code), vim.log.levels.ERROR)
			end
		end)
	end)
end

function M.close()
	state.quitting = true
	if state.proc then
		state.proc:kill(15)
		state.proc = nil
	end
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

return M
