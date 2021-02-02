package com.herim.kh.web;

import javax.servlet.http.HttpSession;

import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authc.ExcessiveAttemptsException;
import org.apache.shiro.authc.IncorrectCredentialsException;
import org.apache.shiro.authc.LockedAccountException;
import org.apache.shiro.authc.UnknownAccountException;
import org.apache.shiro.authc.UsernamePasswordToken;
import org.apache.shiro.subject.Subject;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import com.herim.kh.domain.Assessment;
import com.herim.kh.domain.User;
import com.herim.kh.exceptionhandler.MyException;
import com.herim.kh.service.DeptService;
import com.herim.kh.service.OperationService;
import com.herim.kh.service.PositionService;
import com.herim.kh.service.UserService;
import com.herim.kh.utils.Message;
import com.herim.kh.utils.PasswordEncryption;

@Controller
@RequestMapping("/user")
public class UserController {
	
	@Autowired
	private UserService userService;
	
	@Autowired
	private PositionService positionService;
	
	@Autowired
	private DeptService deptService;
	
	@Autowired
	private OperationService operationService;
	
	/**
	 * 跳转登陆页面
	 * @return
	 */
	@RequestMapping("/to-login")
	public String toLogin() {
		return "login";
	}
	
	/**
	 * 登陆
	 * @param name
	 * @param password
	 * @return
	 */
	@RequestMapping("/login")
	@ResponseBody
	public Message<User> login(@RequestBody User user) {
		Message<User> message = new Message<User>();
		Subject subject = SecurityUtils.getSubject();	
		UsernamePasswordToken token = new UsernamePasswordToken(user.getName(),user.getPassword());
		try {
			subject.login(token);
			message.setCode(Message.OK);
			message.setMsg("登陆成功");
			message.setUrl("/user/to-assess");
			user = userService.findByName(user.getName());
			user.setPassword(null);
			subject.getSession().setAttribute("user", user);
		} catch (UnknownAccountException e) {
			message.setMsg("未知账户");
		} catch (IncorrectCredentialsException e) {
			message.setMsg("密码错误");
		} catch (LockedAccountException e) {
			message.setMsg("账户已被锁定");
		} catch (ExcessiveAttemptsException e) {
			message.setMsg("密码错误次数超过3次");
		} catch (Exception e) {
			message.setMsg("未知错误");
		}
		return message;
	}
	
	/**
	 * 登出
	 * @return
	 */
	@RequestMapping("/logout")
	public String logout() {
		Subject subject = SecurityUtils.getSubject();
	    subject.logout();
		return "redirect:/user/to-login";
	}
	
	@RequestMapping("/test")
	public String test() {
		return "test";
	}
	
	/**
	 * 跳转注册页面
	 * @param model
	 * @return
	 */
	@RequestMapping("/to-register")
	public String toRegister(Model model) {
		model.addAttribute("positions", positionService.findAllPostions());
		model.addAttribute("depts", deptService.findAllDepts());
		return "register";
	}
	
	/**
	 * 注册
	 * @param user
	 * @return
	 */
	@RequestMapping(value = "/register",method = RequestMethod.POST)
	@ResponseBody
	public Message<User> register(@RequestBody User user) {
		Message<User> message = new Message<User>();
		if(userService.findByName(user.getName()) != null) {
			message.setMsg("该用户已经注册。");
			message.setCode(1);
		} else {
			User nuser = userService.addUser(user);
			message.setUrl("/user/to-login");
			message.setData(nuser);
			message.setMsg("注册成功。");
			message.setCode(0);
		}
		return message;
	}

	/**
	 * 跳转打分页面
	 * @param model
	 * @return
	 */
	@RequestMapping("/to-assess")
	public String toAssess(Model model, HttpSession session) {
		User user = (User) session.getAttribute("user");
		if(user != null) {
			model.addAttribute("assessmentsa", userService.findMyAssessmentsByType(user, "A"));
			model.addAttribute("assessmentsb", userService.findMyAssessmentsByType(user, "B"));
			model.addAttribute("assessmentsc", userService.findMyAssessmentsByType(user, "C"));
		}
		return "assess";
	}
	
	
	/**
	 * 生成考核任务
	 * @param user
	 * @return
	 * @throws MyException 
	 */
	@RequestMapping("/generate/{id}")
	@ResponseBody
	public Message generateAssessment(@PathVariable String id) throws MyException {
		Message message = new Message();
		if(operationService.haveOperation("generate", 1)) {
			User user = userService.findById(id);
			userService.generateMyAssessment(user);
			//登出
			Subject subject = SecurityUtils.getSubject();
			subject.logout();
			message.setUrl("/user/to-login");
			message.setMsg("ok");
			message.setCode(0);
		} else {
			message.setMsg("还未开放此功能，请等待通知。");
		}
		return message;
	}
	
	/**
	 * 生成所有考核任务
	 * @param id
	 * @return
	 * @throws MyException
	 */
	@RequestMapping("/generate/all")
	@ResponseBody
	public Message generateAssessment() throws MyException {
		Message message = new Message();
		if(operationService.haveOperation("generate", 1)) {
			userService.generateMyAssessment();
			message.setMsg("ok");
			message.setCode(0);
		} else {
			message.setMsg("还未开放此功能，请等待通知。");
		}
		return message;
	}
	
	
	
	/**
	 * 打分
	 * @param id
	 * @return
	 * @throws MyException
	 */
	@RequestMapping("/rating")
	@ResponseBody
	public Message generateAssessment(@RequestBody Assessment assessment) throws MyException {
		Message message = new Message();
		if(operationService.haveOperation("rating", 1)) {
			userService.rating(assessment);
			message.setMsg("ok");
			message.setCode(0);
		}else {
			message.setCode(1);
			message.setMsg("还未开放此功能，请等待通知。");
		}
		
		return message;
	}
	/**
	 * 修改密码
	 * @param user
	 * @return
	 * @throws MyException
	 */
	@RequestMapping(value = "/password",method = RequestMethod.POST)
	@ResponseBody
	public Message changePassword(@RequestParam String id,@RequestParam String oldpwd,@RequestParam String newpwd) throws MyException {
		Message message = new Message();
		User me = userService.findById(id);
		if(me != null && me.getPassword().equals(PasswordEncryption.encrypt(oldpwd, me.getName()))) {
			userService.changeMyPassword(id,PasswordEncryption.encrypt(newpwd, me.getName()));
			//登出
			Subject subject = SecurityUtils.getSubject();
			subject.logout();
			message.setUrl("/user/to-login");
			message.setMsg("ok");
			message.setCode(0);
		} else {
			message.setMsg("修改密码失败");
		}
		return message;
	}
	
	
	@RequestMapping("/add")
	@ResponseBody
	public Message<User> addUser(@RequestBody User user) {
		Message<User> message = new Message<User>();
		User nuser = userService.addUser(user);
		message.setUrl("/user/to-login");
		message.setData(nuser);
		message.setMsg("添加用户成功");
		message.setCode(0);
		return message;
	}
	
}
