package com.herim.kh.exceptionhandler;

import javax.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.servlet.ModelAndView;
import org.springframework.web.servlet.NoHandlerFoundException;

import com.herim.kh.utils.Message;

@ControllerAdvice
public class GlobalExceptionHandler {

	public static final String DEFAULT_ERROR_VIEW = "error";
	public static final String DEFAULT_NOTFOUND_VIEW = "404";

	@ExceptionHandler(NoHandlerFoundException.class)
	@ResponseStatus(value = HttpStatus.NOT_FOUND)
	public ModelAndView defaultErrorHandler404(HttpServletRequest req, Exception e) throws Exception {
		ModelAndView mav = new ModelAndView();
		mav.addObject("exception", e);
		mav.addObject("url", req.getRequestURL());
		mav.setViewName(DEFAULT_NOTFOUND_VIEW);
		return mav;
	}
	@ExceptionHandler(value = MyException.class)
	@ResponseBody
	public Message<String> jsonErrorHandler(HttpServletRequest req, MyException e) throws Exception {
		Message<String> message = new Message<>();
		message.setMsg(e.getMessage());
		message.setCode(Message.ERROR);
		message.setUrl(req.getRequestURL().toString());
		return message;
	}
    @ExceptionHandler(Throwable.class)
    public ModelAndView defaultErrorHandler(HttpServletRequest req, Exception e) throws Exception {
        ModelAndView mav = new ModelAndView();
        mav.addObject("exception", e);
        mav.addObject("url", req.getRequestURL());
        mav.setViewName(DEFAULT_ERROR_VIEW);
        return mav;
    }
    
    
}
