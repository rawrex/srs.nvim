local state = require("srs.state")
local render = require("srs.render")

local M = {}

local quit_fn = nil

-- Fixed rating keys; the client owns them, the backend only receives the name.
local RATINGS = { n = "Again", e = "Hard", i = "Good", o = "Easy" }

local function send(kind, extra)
	if state.proc then
		state.proc:write(vim.json.encode(vim.tbl_extend("force", { type = kind }, extra or {})) .. "\n")
	end
end

local function bind(buf, lhs, fn)
	if not state.valid_buf(buf) then
		return
	end
	vim.keymap.set("n", lhs, fn, { buffer = buf })
	state.keymaps[buf] = state.keymaps[buf] or {}
	state.keymaps[buf][lhs] = true
end

local function answered()
	if state.mode ~= "question" then
		return
	end
	render.reveal(state.card)
	state.mode = "rating"
	send("answered")
	render.statusline(false)
end

local function pause()
	if state.mode ~= "question" then
		return
	end
	state.paused = not state.paused
	send("pause")
	render.statusline(state.paused)
end

local function skip()
	if state.mode ~= "question" then
		return
	end
	send("skip")
end

local function bind_card_keys()
	local buf = state.buf
	bind(buf, "<CR>", answered)
	bind(buf, "<Space>", pause)
	bind(buf, "<Esc>", skip)
	for key, name in pairs(RATINGS) do
		bind(buf, key, function()
			if state.mode == "rating" then
				state.mode = "idle"
				send("rate", { rating = name })
			end
		end)
	end
	if quit_fn then
		bind(buf, "<C-c>", quit_fn)
	end
end

local function handle_message(message)
	local kind = message.type
	if kind == "intro" then
		if message.cloze then
			state.cloze_open = message.cloze.open or state.cloze_open
			state.cloze_close = message.cloze.close or state.cloze_close
		end
		vim.notify(string.format("srs: %d due card(s)", message.due or 0), vim.log.levels.INFO)
		send("start")
	elseif kind == "card" then
		state.mode = "question"
		state.card = message.card
		state.paused = false
		render.open(message.card)
		bind_card_keys()
		render.statusline(false)
	elseif kind == "notice" then
		if message.text ~= "" then
			vim.notify("srs: " .. message.text, message.level == "error" and vim.log.levels.WARN or vim.log.levels.INFO)
		end
	end
end

function M.setup_keymaps(quit)
	quit_fn = quit
end

function M.start(repo_root, python, rpc_path)
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

	state.proc = vim.system({ python, rpc_path }, {
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
			if state.quitting then
				return
			end
			if completed.code ~= 0 then
				vim.notify("srs: process exited with code " .. tostring(completed.code), vim.log.levels.ERROR)
			end
			state.restore()
		end)
	end)
end

return M
