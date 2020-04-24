package com.herim.kh.domain;

import javax.persistence.Id;
import javax.persistence.Transient;

import lombok.Data;

@Data
public class UserScore {
	
	@Id
	private String userId;
	@Transient
	private User user;
	private Double finalScore;

}
