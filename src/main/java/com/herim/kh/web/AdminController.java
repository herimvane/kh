package com.herim.kh.web;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;

import com.herim.kh.domain.UserScore;
import com.herim.kh.service.UserService;

@Controller
@RequestMapping("/admin")
public class AdminController {

	@Autowired
	private UserService userService;

	/**
	 * 跳转得分情况页面
	 * @param model
	 * @return
	 */
	@RequestMapping("/to-score/{sjdf}")
	public String toScore(Model model, @PathVariable double sjdf) {
		List<UserScore> userScores = userService.calculateAllUsersScore(sjdf);
		model.addAttribute("userScores", userScores);
		return "score";
	}
}
