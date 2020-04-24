package com.herim.kh.service;

import java.util.List;

import com.herim.kh.domain.Assessment;
import com.herim.kh.domain.Position;
import com.herim.kh.domain.User;
import com.herim.kh.domain.UserScore;
import com.herim.kh.exceptionhandler.MyException;

public interface UserService {
	
	User findByName(String name);
	User findById(String id);
	User addUser(User user);
	List<Assessment> findMyAssessments(User user);
	List<Assessment> findMyAssessmentsByType(User user,String type);
	void updateUserStatus(Integer status, String id);
	void generateMyAssessment(User user) throws MyException;
	List<User> findByPosition(Position position);
	void rating(Assessment assessment);
	List<UserScore> calculateAllUsersScore(double sjdf);
	void changeMyPassword(String id,String password);
	void generateMyAssessment() throws MyException;

	
}
