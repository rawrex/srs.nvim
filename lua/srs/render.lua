local state = require("srs.state")

local M = {}

local CLOZE_HL = "SrsCloze"

local function escape_pattern(text)
	return (text:gsub("([%^%$%(%)%%%.%[%]%*%+%-%?])", "%%%1"))
end

local function clear_current()
	if state.valid_buf(state.buf) then
		vim.api.nvim_buf_clear_namespace(state.buf, state.ns, 0, -1)
		state.clear_folds(state.win)
	end
end

local function save_window(win)
	if state.saved_win then
		return
	end
	state.saved_win = {
		foldmethod = vim.wo[win].foldmethod,
		foldenable = vim.wo[win].foldenable,
		foldlevel = vim.wo[win].foldlevel,
		statusline = vim.wo[win].statusline,
	}
end

local function cloze_mask(width)
	return string.rep("█", math.max(width, 1))
end

local function mask_clozes(buf, lines)
	local pattern = escape_pattern(state.cloze_open) .. ".-" .. escape_pattern(state.cloze_close)
	for row, line in ipairs(lines) do
		local init = 1
		while true do
			local start_col, end_col = line:find(pattern, init)
			if not start_col then
				break
			end
			local width = vim.fn.strdisplaywidth(line:sub(1, end_col))
				- vim.fn.strdisplaywidth(line:sub(1, start_col - 1))
			vim.api.nvim_buf_set_extmark(buf, state.ns, row - 1, start_col - 1, {
				virt_text = { { cloze_mask(width), CLOZE_HL } },
				virt_text_pos = "overlay",
				priority = 100,
			})
			init = end_col + 1
		end
	end
end

local function fold_blocks(win, lines)
	local first, last = nil, nil
	local function flush()
		if first and last and last > first then
			state.win_cmd(win, string.format("silent! %d,%dfold", first, last))
		end
		first, last = nil, nil
	end
	for i, line in ipairs(lines) do
		if line:match("^%s*>") then
			if not first then
				first = i
			end
			last = i
		else
			flush()
		end
	end
	flush()
end

function M.open(card)
	vim.api.nvim_set_hl(0, CLOZE_HL, { link = "Comment", default = true })
	local win = state.win
	if not state.valid_win(win) or not card or not card.note then
		return
	end

	local abs = (state.repo_root or "") .. card.note
	local buf = vim.fn.bufadd(abs)
	vim.fn.bufload(buf)

	if state.buf ~= buf then
		clear_current()
		state.buf = buf
		state.touched[buf] = true
	end
	save_window(win)
	vim.api.nvim_win_set_buf(win, buf)

	vim.wo[win].foldmethod = "manual"
	vim.wo[win].foldenable = true

	clear_current()
	local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
	mask_clozes(buf, lines)
	fold_blocks(win, lines)
	vim.wo[win].foldlevel = 0

	local line = math.min(card.start_line or 1, #lines)
	if line >= 1 then
		vim.api.nvim_win_set_cursor(win, { line, 0 })
	end
end

function M.reveal(card)
	local buf, win = state.buf, state.win
	if not card or not state.valid_buf(buf) then
		return
	end
	local last = math.min(card.end_line or 1, vim.api.nvim_buf_line_count(buf))
	vim.api.nvim_buf_clear_namespace(buf, state.ns, (card.start_line or 1) - 1, last)
	state.win_cmd(win, string.format("silent! %d,%dfoldopen!", card.start_line or 1, last))
end

function M.statusline(paused)
	local win = state.win
	if not state.valid_win(win) then
		return
	end
	local card = state.card
	local name = ""
	if card and card.note and card.note ~= "" then
		name = card.note:gsub("^/", "") .. " "
	end
	local suffix = paused and " (PAUSED)" or ""
	local hint = state.mode == "rating" and " | n/e/i/o" or ""
	vim.wo[win].statusline = string.format(
		"[%d/%d] %s%s%s",
		card and card.index or 0,
		card and card.total or 0,
		name,
		suffix,
		hint
	)
end

return M
